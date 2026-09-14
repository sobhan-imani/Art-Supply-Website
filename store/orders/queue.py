"""A small database backed queue for the work that follows an order.

Why not do it inline in the checkout view? Because a mail server that hangs, an
sms gateway that rate limits or a worker that is restarted mid deploy must never
turn into a failed checkout or a lost order. Checkout writes the order and one
queued row; the worker does the rest and retries on its own.

Why not Celery? Because this needs no extra service in production: the rows live
in the database that is deployed anyway. ``run_job`` is the only thing a Celery
task would have to call, so moving over later is a handful of lines.
"""

import logging
import traceback

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import OrderJob

logger = logging.getLogger(__name__)

# Wait this many seconds before retry 1, 2, 3 ... (the last value repeats).
RETRY_BACKOFF = (60, 300, 900, 3600)

_handlers = {}


def handler(kind):
    """Register a function as the handler for one job kind."""
    def register(function):
        _handlers[kind] = function
        return function
    return register


def enqueue(order, kind, run_at=None, max_attempts=5):
    """Put one job on the queue. Safe to call inside the checkout transaction."""
    if kind not in _handlers:
        raise ValueError(f'no handler registered for job kind {kind!r}')
    return OrderJob.objects.create(order=order, kind=kind, max_attempts=max_attempts,
                                   run_at=run_at or timezone.now())


def claim_job():
    """Take the next due job, or return ``None`` when the queue is empty.

    ``skip_locked`` is what lets several workers (or several web dynos running
    the command) share the queue without ever handing the same job out twice.
    """
    with transaction.atomic():
        job = (OrderJob.objects.select_for_update(skip_locked=True)
               .filter(status=OrderJob.QUEUED, run_at__lte=timezone.now())
               .order_by('run_at', 'id').first())
        if job is None:
            return None
        job.status = OrderJob.RUNNING
        job.attempts += 1
        job.save(update_fields=['status', 'attempts'])
        return job


def run_job(job):
    """Run one claimed job, marking it done or scheduling a retry."""
    try:
        with transaction.atomic():
            _handlers[job.kind](job.order)
    except Exception:
        _fail(job, traceback.format_exc())
        return False

    job.status = OrderJob.DONE
    job.last_error = ''
    job.finished_at = timezone.now()
    job.save(update_fields=['status', 'last_error', 'finished_at'])
    return True


def _fail(job, error):
    logger.warning('order job %s (%s) failed on attempt %s', job.pk, job.kind, job.attempts)
    job.last_error = error[-2000:]
    if job.attempts >= job.max_attempts:
        job.status = OrderJob.FAILED
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at'])
        return
    delay = RETRY_BACKOFF[min(job.attempts - 1, len(RETRY_BACKOFF) - 1)]
    job.status = OrderJob.QUEUED
    job.run_at = timezone.now() + timezone.timedelta(seconds=delay)
    job.save(update_fields=['status', 'last_error', 'run_at'])


def process_jobs(limit=None):
    """Drain the due jobs. Returns ``(done, failed)``."""
    done = failed = 0
    while limit is None or done + failed < limit:
        job = claim_job()
        if job is None:
            break
        if run_job(job):
            done += 1
        else:
            failed += 1
    return done, failed


@handler('confirm_order')
def confirm_order(order):
    """Accept the order into the shop's own queue of work to do."""
    if order.status == 'new':
        order.log('pending', _('Order received and waiting to be processed.'))


@handler('notify_customer')
def notify_customer(order):
    """Tell the customer their order is in. Slow and flaky, hence off-request."""
    user = order.profile.user if order.profile else None
    if not (user and user.email):
        logger.info('order %s has no e-mail address to notify', order.pk)
        return
    send_mail(
        subject=_('Your order #%(number)s') % {'number': order.pk},
        message=_('Thank you! Order #%(number)s totalling %(total)s is being prepared.')
                % {'number': order.pk, 'total': order.price},
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )


@handler('expire_unpaid_order')
def expire_unpaid_order(order):
    """Give the reserved stock back when a customer never pays.

    Queued with a run_at when the order is placed, so no separate cron job is
    needed, and dropped again the moment the payment arrives.
    """
    from .services import cancel_order  # imported here to keep the modules acyclic

    order.refresh_from_db()
    if order.status != order.AWAITING_PAYMENT:
        return  # paid or already off: nothing to reclaim
    cancel_order(order, note=_('Not paid in time, the items were released.'))
    logger.info('order %s expired without payment', order.pk)
