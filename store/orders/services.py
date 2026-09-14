"""What happens to an order, independent of who asked.

The views, the queue workers and the payment callback all need the same two
operations, so they live here rather than as private helpers of a view.
"""

from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext as _

from products.models import Item

from .models import Order, OrderItem, OrderJob
from .queue import enqueue


class OutOfStock(Exception):
    """Raised when an item sold out before the order could reserve it."""

    def __init__(self, item):
        self.item = item
        super().__init__(f'{item} is out of stock')


@transaction.atomic
def place_order(cart, profile, address):
    """Turn a cart into an order, holding back the stock it consumes.

    Reserving stock is the one step that cannot be deferred without risking an
    oversell, so it stays inside the request. Everything slow is queued instead,
    see orders/queue.py.
    """
    rows = list(cart)
    # Lock the item rows in primary key order, so two checkouts sharing two
    # items cannot deadlock, then re-read their stock inside that lock.
    locked = {item.pk: item for item in
              Item.objects.select_for_update().filter(
                  pk__in=[row['item'].pk for row in rows]).order_by('pk')}
    for row in rows:
        item = locked.get(row['item'].pk)
        if item is None or item.stock < row['quantity']:
            raise OutOfStock(row['item'])

    order = Order.objects.create(
        profile=profile,
        address=address,
        price=cart.get_total_price(),
        status=Order.AWAITING_PAYMENT,
        is_ordered=True,
    )
    OrderItem.objects.bulk_create([
        OrderItem(order=order, item=row['item'], quantity=row['quantity'], price=row['price'])
        for row in rows
    ])
    for row in rows:
        # A conditional update instead of read-modify-write, so the last piece
        # cannot be sold twice even on a backend that ignores row locks (sqlite).
        taken = (Item.objects.filter(pk=row['item'].pk, stock__gte=row['quantity'])
                 .update(stock=F('stock') - row['quantity']))
        if not taken:
            raise OutOfStock(row['item'])

    order.log(Order.AWAITING_PAYMENT, _('Order placed, waiting for payment.'))
    # The stock is held for the customer, but not forever: if they never pay,
    # this hands it back. Queued, so no cron job of its own is needed.
    enqueue(order, 'expire_unpaid_order', run_at=order.payment_deadline())
    cart.clear()
    return order


@transaction.atomic
def mark_order_paid(order):
    """Move a paid order into the shop queue. Safe to call twice."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status != Order.AWAITING_PAYMENT:
        # Already paid, or already cancelled: a repeated gateway callback must
        # not queue the confirmation mails a second time.
        return locked

    locked.log('new', _('Payment received.'))
    # Nothing slow in the request: a mail server that hangs is the queue's problem.
    enqueue(locked, 'confirm_order')
    enqueue(locked, 'notify_customer')
    _drop_queued_jobs(locked, 'expire_unpaid_order')
    return locked


@transaction.atomic
def cancel_order(order, note=None, status='canceled'):
    """Cancel the order and hand the stock it reserved back to the shop."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if not locked.can_be_canceled:
        return locked
    for row in locked.order_items.all():
        Item.objects.filter(pk=row.item_id).update(stock=F('stock') + row.quantity)
    # No point in still confirming or announcing an order that is off.
    _drop_queued_jobs(locked)
    locked.log(status, note or _('Canceled by the customer.'))
    return locked


def _drop_queued_jobs(order, kind=None):
    jobs = order.jobs.filter(status=OrderJob.QUEUED)
    if kind:
        jobs = jobs.filter(kind=kind)
    jobs.delete()
