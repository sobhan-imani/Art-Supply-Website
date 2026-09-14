"""Paying for an order.

The shop talks to one `Gateway` object and never to a provider directly, so
connecting a real one later means writing a class here and pointing the
PAYMENT_GATEWAY setting at it: no view, template or test has to change.

Two rules every gateway has to keep:

* `start` may only hand back a URL to send the customer to. It must not mark
  anything as paid.
* `verify` is called on the way back and may be called more than once for the
  same payment (customers refresh, gateways retry). It must be a question about
  the payment, never an action with side effects of its own.
"""

import logging

from django.conf import settings
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.module_loading import import_string

from .models import Payment

logger = logging.getLogger(__name__)


class Gateway:
    """What the shop expects of a payment provider."""

    name = 'gateway'

    def start(self, payment, request) -> str:
        """Prepare the attempt and return the URL to send the customer to."""
        raise NotImplementedError

    def verify(self, payment, request) -> bool:
        """Did this payment actually go through?"""
        raise NotImplementedError


class DummyGateway(Gateway):
    """A stand-in that approves everything, for development and tests.

    It still walks the whole road: a token is issued, the customer is sent to a
    page that mimics the provider, and the callback is verified. Only the
    network call to a bank is missing, which is what makes it safe to run.
    """

    name = 'dummy'

    def start(self, payment, request) -> str:
        payment.token = get_random_string(24)
        payment.save(update_fields=['token'])
        logger.info('dummy gateway: sending order %s to the payment page', payment.order_id)
        return reverse('orders:payment_dummy', args=[payment.token])

    def verify(self, payment, request) -> bool:
        # The dummy page posts back the outcome the tester picked.
        return request.POST.get('outcome', 'paid') == 'paid'


def get_gateway() -> Gateway:
    """The gateway this deployment is configured with."""
    path = getattr(settings, 'PAYMENT_GATEWAY', 'orders.payment.DummyGateway')
    return import_string(path)()


def start_payment(order, request) -> tuple:
    """Open a payment attempt for an order and say where the customer goes next.

    Reuses a pending attempt instead of piling up rows when a customer goes back
    and clicks pay again.
    """
    gateway = get_gateway()
    payment = order.payments.filter(status=Payment.PENDING, gateway=gateway.name).first()
    if payment is None or payment.amount != order.price:
        payment = Payment.objects.create(order=order, amount=order.price, gateway=gateway.name)
    return payment, gateway.start(payment, request)
