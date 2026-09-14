from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from products.models import Item

from . import queue
from .models import Order, OrderJob, Payment
from .payment import Gateway
from .tests import ADDRESS, pay

User = get_user_model()


class OtherGateway(Gateway):
    """Stands in for a real provider: anything that is not the dummy one."""

    name = 'other'

    def start(self, payment, request):
        payment.token = 'other-token'
        payment.save(update_fields=['token'])
        return '/gateway/redirect/'

    def verify(self, payment, request):
        return True


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234',
                                             email='customer@example.com')
        self.client.force_login(self.user)
        self.order = self.checkout()

    def checkout(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 2})
        self.client.post(reverse('orders:checkout'), ADDRESS)
        return Order.objects.get()

    def test_checkout_reserves_the_stock_before_any_payment(self):
        # The customer has not paid, but nobody else can buy these two either.
        self.assertEqual(self.order.status, Order.AWAITING_PAYMENT)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 3)

    def test_going_to_pay_opens_an_attempt_and_sends_the_customer_on(self):
        response = self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        payment = self.order.payments.get()
        self.assertEqual(payment.amount, self.order.price)
        self.assertEqual(payment.status, Payment.PENDING)
        self.assertRedirects(response, reverse('orders:payment_dummy', args=[payment.token]))

    def test_the_gateway_page_renders_with_a_way_to_pay(self):
        self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        payment = self.order.payments.get()
        response = self.client.get(reverse('orders:payment_dummy', args=[payment.token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('orders:payment_callback', args=[payment.pk]))
        self.assertContains(response, '20.00')

    def test_the_receipt_and_the_tracking_page_render_for_a_paid_order(self):
        pay(self.client, self.order)
        for url in (reverse('orders:order_success', args=[self.order.pk]),
                    reverse('orders:order_detail', args=[self.order.pk]),
                    reverse('account_profile')):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_an_unpaid_order_is_shown_as_unpaid_not_as_a_thank_you(self):
        response = self.client.get(reverse('orders:order_success', args=[self.order.pk]))
        self.assertContains(response, 'waiting for payment')
        self.assertContains(response, reverse('orders:payment_start', args=[self.order.pk]))

    def test_clicking_pay_twice_reuses_the_same_attempt(self):
        self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        self.assertEqual(self.order.payments.count(), 1)

    def test_a_successful_payment_moves_the_order_on(self):
        response = pay(self.client, self.order)

        self.assertRedirects(response, reverse('orders:order_success', args=[self.order.pk]))
        self.assertEqual(self.order.status, 'new')
        self.assertTrue(self.order.is_paid)
        payment = self.order.payments.get()
        self.assertEqual(payment.status, Payment.PAID)
        self.assertIsNotNone(payment.paid_at)
        self.assertTrue(self.order.events.filter(status='new').exists())

    def test_a_successful_payment_queues_the_confirmation_work(self):
        pay(self.client, self.order)
        self.assertEqual(sorted(job.kind for job in self.order.jobs.filter(status=OrderJob.QUEUED)),
                         ['confirm_order', 'notify_customer'])
        # And the deadline that would have freed the stock is gone.
        self.assertFalse(self.order.jobs.filter(kind='expire_unpaid_order').exists())
        self.assertEqual(len(mail.outbox), 0)  # still nothing slow in the request

    def test_a_replayed_callback_does_not_order_or_notify_twice(self):
        self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        payment = self.order.payments.get()
        url = reverse('orders:payment_callback', args=[payment.pk])

        self.client.post(url, {'outcome': 'paid'})
        self.client.post(url, {'outcome': 'paid'})

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.order.jobs.filter(kind='notify_customer').count(), 1)
        self.assertEqual(self.order.events.filter(status='new').count(), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 3)  # not charged twice against the stock

    def test_a_failed_payment_leaves_the_order_payable(self):
        self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        payment = self.order.payments.get()
        response = self.client.post(reverse('orders:payment_callback', args=[payment.pk]),
                                    {'outcome': 'failed'})

        self.assertRedirects(response, reverse('orders:order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.FAILED)
        self.assertEqual(self.order.status, Order.AWAITING_PAYMENT)
        self.assertContains(self.client.get(reverse('orders:order_detail', args=[self.order.pk])),
                            reverse('orders:payment_start', args=[self.order.pk]))

    def test_a_customer_cannot_pay_for_somebody_elses_order(self):
        self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        payment = self.order.payments.get()

        other = User.objects.create_user(phone_number='09120000001', password='secret1234')
        self.client.force_login(other)
        self.assertEqual(self.client.get(
            reverse('orders:payment_start', args=[self.order.pk])).status_code, 404)
        self.assertEqual(self.client.post(
            reverse('orders:payment_callback', args=[payment.pk])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse('orders:payment_dummy', args=[payment.token])).status_code, 404)

    def test_the_callback_only_takes_a_post(self):
        self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        payment = self.order.payments.get()
        self.assertEqual(self.client.get(
            reverse('orders:payment_callback', args=[payment.pk])).status_code, 405)

    def test_paying_needs_a_login(self):
        self.client.logout()
        response = self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)

    def test_an_already_paid_order_goes_to_its_receipt(self):
        pay(self.client, self.order)
        response = self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        self.assertRedirects(response, reverse('orders:order_success', args=[self.order.pk]))

    @override_settings(PAYMENT_GATEWAY='orders.test_payment.OtherGateway')
    def test_another_gateway_takes_over_without_touching_the_views(self):
        response = self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        self.assertEqual(response.url, '/gateway/redirect/')
        payment = self.order.payments.get()
        self.assertEqual(payment.gateway, 'other')
        # And the test page of the dummy gateway is closed off.
        self.assertEqual(self.client.get(
            reverse('orders:payment_dummy', args=[payment.token])).status_code, 404)


class UnpaidOrderExpiryTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.force_login(self.user)
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 2})
        self.client.post(reverse('orders:checkout'), ADDRESS)
        self.order = Order.objects.get()

    def test_the_deadline_is_queued_for_later_not_now(self):
        job = self.order.jobs.get(kind='expire_unpaid_order')
        self.assertGreater(job.run_at, timezone.now())
        self.assertEqual(queue.process_jobs(), (0, 0))  # not due, so nothing runs

    def test_when_it_runs_the_stock_goes_back_on_sale(self):
        self.order.jobs.update(run_at=timezone.now())
        done, failed = queue.process_jobs()

        self.assertEqual((done, failed), (1, 0))
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.status, 'canceled')
        self.assertEqual(self.item.stock, 5)
        self.assertTrue(self.order.events.filter(status='canceled').exists())

    def test_an_order_paid_just_in_time_is_left_alone(self):
        pay(self.client, self.order)
        # The deadline job is dropped on payment, but even a stale copy is safe.
        OrderJob.objects.create(order=self.order, kind='expire_unpaid_order')
        queue.process_jobs()

        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')  # confirm_order ran, not the expiry
        self.assertEqual(self.item.stock, 3)

    def test_the_expired_order_can_no_longer_be_paid(self):
        self.order.jobs.update(run_at=timezone.now())
        queue.process_jobs()
        response = self.client.get(reverse('orders:payment_start', args=[self.order.pk]))
        self.assertRedirects(response, reverse('orders:order_detail', args=[self.order.pk]))
        self.assertEqual(self.order.payments.count(), 0)
