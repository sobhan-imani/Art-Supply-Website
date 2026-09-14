from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel
from customers.models import Address, Profile
from products.models import Item


class Order(BaseModel):
    AWAITING_PAYMENT = 'awaiting'
    STATUS = (
        (AWAITING_PAYMENT, _('Awaiting payment')),
        ('new', _('New')),
        ('pending', _('Pending')),
        ('accepted', _('Accepted')),
        ('rejected', _('Rejected')),
        ('canceled', _('Canceled')),
        ('delivered', _('Delivered')),
    )
    # The steps an order walks through, in the order the tracking page shows them.
    TRACKING_STEPS = (AWAITING_PAYMENT, 'new', 'pending', 'accepted', 'delivered')
    # Past these the order is finished and nothing can be changed anymore.
    CLOSED_STATUSES = ('rejected', 'canceled', 'delivered')
    # While in these, the stock is reserved and the customer may still call it off.
    CANCELABLE_STATUSES = (AWAITING_PAYMENT, 'new', 'pending')

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ('-created_at', '-id')
        indexes = [models.Index(fields=['profile', 'status'])]
    profile = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True,verbose_name=_('Profile'), related_name='orders')
    price = models.DecimalField(_('Price'), max_digits=9, decimal_places=2)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('Address'))
    status = models.CharField(_('Status'), max_length=10, choices=STATUS, default='new')
    items = models.ManyToManyField(Item, related_name='orders',through='OrderItem', verbose_name=_('Items'))
    last_modified = models.DateTimeField(_('Last Modified'), auto_now=True)
    is_ordered = models.BooleanField(_('Is Ordered'), default=False)
    def __str__(self):
        # profile is nullable, so an order outliving its customer must still print
        owner = self.profile.user.phone_number if self.profile else _('Unknown customer')
        return f"{owner} Order-{self.pk}"

    def get_absolute_url(self):
        return reverse('orders:order_detail', args=[self.pk])

    @property
    def total_quantity(self):
        return sum(row.quantity for row in self.order_items.all())

    @property
    def is_closed(self):
        return self.status in self.CLOSED_STATUSES

    @property
    def can_be_canceled(self):
        return self.status in self.CANCELABLE_STATUSES

    @property
    def is_paid(self):
        return self.status not in (self.AWAITING_PAYMENT, 'canceled', 'rejected')

    def payment_deadline(self):
        """When an unpaid order gives its reserved stock back."""
        minutes = getattr(settings, 'PAYMENT_DEADLINE_MINUTES', 30)
        return (self.created_at or timezone.now()) + timezone.timedelta(minutes=minutes)

    def tracking_steps(self):
        """The timeline the tracking page draws: one entry per expected step."""
        events = {event.status: event for event in self.events.all()}
        # A canceled or rejected order stops walking the line: only the steps it
        # really logged count as done.
        stopped = self.is_closed and self.status != 'delivered'
        reached = (self.TRACKING_STEPS.index(self.status)
                   if self.status in self.TRACKING_STEPS else len(self.TRACKING_STEPS))
        steps = []
        for index, status in enumerate(self.TRACKING_STEPS):
            event = events.get(status)
            steps.append({
                'status': status,
                'label': dict(self.STATUS)[status],
                'done': event is not None if stopped else index <= reached,
                'current': status == self.status,
                'event': event,
            })
        return steps

    def log(self, status=None, note=''):
        """Record a tracking event, and move the order there when a status is given."""
        if status and status != self.status:
            self.status = status
            self.save(update_fields=['status', 'last_modified'])
        return OrderEvent.objects.create(order=self, status=status or self.status, note=note)

class OrderItem(BaseModel):
    class Meta:
        verbose_name = _("Order Item")
        verbose_name_plural = _("Order Items")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name=_('Order'), related_name='order_items')
    item = models.ForeignKey(Item, on_delete=models.CASCADE, verbose_name=_('Item'))
    quantity = models.PositiveIntegerField(_('Quantity'), default=1)
    # Unit price the customer was charged; the catalog price may change later.
    price = models.DecimalField(_('Price'), max_digits=8, decimal_places=2, default=0)

    @property
    def total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity} of {self.item.name} in {self.order}"


class OrderEvent(BaseModel):
    """One line of an order's history, shown on the tracking page."""

    class Meta:
        verbose_name = _("Order Event")
        verbose_name_plural = _("Order Events")
        ordering = ('created_at', 'id')

    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name=_('Order'), related_name='events')
    status = models.CharField(_('Status'), max_length=10, choices=Order.STATUS)
    note = models.CharField(_('Note'), max_length=200, blank=True, default='')

    def __str__(self):
        return f"{self.order} -> {self.get_status_display()}"


class OrderJob(BaseModel):
    """A unit of after-the-order work, kept in the database instead of in the request.

    Checkout only reserves the stock and writes the order; anything slow or
    failure prone (mail, sms, an external payment or warehouse call) is queued
    here and picked up by ``manage.py process_order_jobs``. Nothing is lost when
    a worker dies or is restarted during a deploy: the row simply stays queued.
    """

    QUEUED = 'queued'
    RUNNING = 'running'
    DONE = 'done'
    FAILED = 'failed'
    STATUS = (
        (QUEUED, _('Queued')),
        (RUNNING, _('Running')),
        (DONE, _('Done')),
        (FAILED, _('Failed')),
    )

    class Meta:
        verbose_name = _("Order Job")
        verbose_name_plural = _("Order Jobs")
        ordering = ('run_at', 'id')
        indexes = [models.Index(fields=['status', 'run_at'])]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name=_('Order'), related_name='jobs')
    kind = models.CharField(_('Kind'), max_length=40)
    status = models.CharField(_('Status'), max_length=10, choices=STATUS, default=QUEUED)
    run_at = models.DateTimeField(_('Run at'), default=timezone.now)
    attempts = models.PositiveSmallIntegerField(_('Attempts'), default=0)
    max_attempts = models.PositiveSmallIntegerField(_('Max Attempts'), default=5)
    last_error = models.TextField(_('Last Error'), blank=True, default='')
    finished_at = models.DateTimeField(_('Finished at'), null=True, blank=True)

    def __str__(self):
        return f"{self.kind} for order {self.order_id} ({self.status})"


class Payment(BaseModel):
    """One attempt at paying for an order.

    Kept as its own row rather than a flag on the order, so a retried or failed
    attempt leaves a trace and a gateway reference can be looked up later.
    """

    PENDING = 'pending'
    PAID = 'paid'
    FAILED = 'failed'
    STATUS = (
        (PENDING, _('Pending')),
        (PAID, _('Paid')),
        (FAILED, _('Failed')),
    )

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ('-created_at', '-id')

    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name=_('Order'),
                              related_name='payments')
    amount = models.DecimalField(_('Amount'), max_digits=9, decimal_places=2)
    gateway = models.CharField(_('Gateway'), max_length=40)
    # What the gateway calls this attempt, and what it calls the settled payment.
    token = models.CharField(_('Token'), max_length=100, blank=True, default='', db_index=True)
    reference = models.CharField(_('Reference'), max_length=100, blank=True, default='')
    status = models.CharField(_('Status'), max_length=10, choices=STATUS, default=PENDING)
    paid_at = models.DateTimeField(_('Paid at'), null=True, blank=True)
    error = models.CharField(_('Error'), max_length=200, blank=True, default='')

    def __str__(self):
        return f"{self.gateway} payment for order {self.order_id} ({self.status})"

    def mark_paid(self, reference=''):
        self.status = self.PAID
        self.reference = reference
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'reference', 'paid_at'])

    def mark_failed(self, error=''):
        self.status = self.FAILED
        self.error = error[:200]
        self.save(update_fields=['status', 'error'])
