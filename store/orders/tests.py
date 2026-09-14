from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from customers.models import Address
from products.models import Item

from . import queue
from .models import Order, OrderItem, OrderJob

User = get_user_model()

ADDRESS = {'country': 'Iran', 'city': 'Tehran', 'street': 'Valiasr Ave', 'postal_code': '123'}


def pay(client, order):
    """Walk the dummy gateway for an order: go to the provider, then come back."""
    client.get(reverse('orders:payment_start', args=[order.pk]))
    payment = order.payments.latest('id')
    response = client.post(reverse('orders:payment_callback', args=[payment.pk]),
                           {'outcome': 'paid', 'reference': payment.token})
    order.refresh_from_db()
    return response


class CartTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.discounted = Item.objects.create(name='Canvas', price=Decimal('20.00'),
                                              stock=3, discount=50)

    def add(self, item, quantity=1):
        return self.client.post(reverse('orders:cart_add', args=[item.id]),
                                {'quantity': quantity})

    def test_add_shows_in_navbar_on_every_page(self):
        self.add(self.item, 2)
        response = self.client.get(reverse('products-list'))
        self.assertContains(response, 'Brush')
        self.assertEqual(len(response.context['cart']), 2)

    def test_cart_totals_use_the_discounted_price(self):
        self.add(self.discounted, 2)
        response = self.client.get(reverse('products-list'))
        self.assertEqual(response.context['cart'].get_total_price(), Decimal('20.00'))

    def test_quantity_is_clamped_to_stock(self):
        self.add(self.item, 99)
        response = self.client.get(reverse('products-list'))
        self.assertEqual(len(response.context['cart']), 5)

    def test_session_only_stores_json_serializable_rows(self):
        self.add(self.item, 2)
        self.client.get(reverse('products-list'))  # iterating the cart must not poison it
        self.assertEqual(self.client.session['cart'], {str(self.item.id): 2})

    def test_update_and_remove(self):
        self.add(self.item, 2)
        self.client.post(reverse('orders:cart_update', args=[self.item.id]), {'quantity': 4})
        self.assertEqual(self.client.session['cart'], {str(self.item.id): 4})
        self.client.post(reverse('orders:cart_remove', args=[self.item.id]))
        self.assertEqual(self.client.session['cart'], {})

    def test_update_to_zero_removes_the_row(self):
        self.add(self.item, 2)
        self.client.post(reverse('orders:cart_update', args=[self.item.id]), {'quantity': 0})
        self.assertEqual(self.client.session['cart'], {})

    def test_deleted_item_falls_out_of_the_cart(self):
        self.add(self.item, 2)
        self.item.delete()
        response = self.client.get(reverse('products-list'))
        self.assertEqual(len(response.context['cart']), 0)

    def test_ajax_add_returns_the_rendered_sidebar(self):
        response = self.client.post(reverse('orders:cart_add', args=[self.item.id]),
                                    {'quantity': 1}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertIn('Brush', payload['html'])

    def test_cart_url_sends_visitors_to_the_shop_with_the_sidebar_open(self):
        response = self.client.get(reverse('orders:cart_summary'))
        self.assertRedirects(response, f"{reverse('products-list')}?cart=open")

    def test_the_message_shows_up_on_the_page_it_lands_on(self):
        response = self.client.post(reverse('orders:cart_add', args=[self.item.id]),
                                    {'quantity': 1}, follow=True)
        self.assertContains(response, 'Brush was added to your cart.')
        self.assertContains(response, 'alert-info')

    def test_a_page_without_messages_has_no_empty_alert_container(self):
        # An always rendered wrapper left a white gap under the navbar.
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'container mt-3')

    def test_plain_form_post_returns_to_the_page_it_came_from(self):
        response = self.client.post(reverse('orders:cart_add', args=[self.item.id]),
                                    {'quantity': 1},
                                    HTTP_REFERER=reverse('product-detail', args=[self.item.id]))
        self.assertRedirects(response, reverse('product-detail', args=[self.item.id]))

    def test_a_foreign_referer_is_not_followed(self):
        response = self.client.post(reverse('orders:cart_add', args=[self.item.id]),
                                    {'quantity': 1}, HTTP_REFERER='https://evil.example.com/')
        self.assertRedirects(response, reverse('products-list'))

    def test_add_requires_post(self):
        self.assertEqual(self.client.get(reverse('orders:cart_add', args=[self.item.id])).status_code, 405)


class CheckoutTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.force_login(self.user)
        self.address_data = {
            'country': 'Iran', 'city': 'Tehran', 'street': 'Fake Street',
            'postal_code': '1234567890',
        }

    def test_empty_cart_cannot_reach_checkout(self):
        response = self.client.get(reverse('orders:checkout'))
        self.assertRedirects(response, reverse('products-list'))

    def test_order_is_placed_from_a_new_address(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 2})
        response = self.client.post(reverse('orders:checkout'), self.address_data)

        order = Order.objects.get()
        self.assertRedirects(response, reverse('orders:payment_start', args=[order.pk]),
                             target_status_code=302)
        self.assertEqual(order.profile, self.user.profile)
        self.assertEqual(order.price, Decimal('20.00'))
        self.assertEqual(order.status, Order.AWAITING_PAYMENT)
        self.assertTrue(order.is_ordered)

        row = OrderItem.objects.get()
        self.assertEqual((row.item, row.quantity, row.price), (self.item, 2, Decimal('10.00')))
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 3)
        self.assertEqual(self.client.session['cart'], {})

    def test_order_is_placed_from_a_saved_address(self):
        address = Address.objects.create(profile=self.user.profile, **self.address_data)
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        response = self.client.post(reverse('orders:checkout'), {'address': address.id})
        order = Order.objects.get()
        self.assertRedirects(response, reverse('orders:payment_start', args=[order.pk]),
                             target_status_code=302)
        self.assertEqual(order.address, address)

    def test_saved_addresses_are_offered_without_blocking_the_form(self):
        Address.objects.create(profile=self.user.profile, **self.address_data)
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        response = self.client.get(reverse('orders:checkout'))
        # The hidden new-address inputs must not be able to block the submit, so
        # the form opts out of browser validation and the view does the checking.
        self.assertContains(response, 'novalidate')
        self.assertContains(response, 'name="address"')

    def test_the_page_does_not_leak_its_own_source_comments(self):
        # {# ... #} only comments a single line; spread over several it is printed.
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        response = self.client.get(reverse('orders:checkout'))
        self.assertNotContains(response, 'novalidate on purpose')

    def test_a_deleted_address_is_not_offered_or_accepted(self):
        address = Address.objects.create(profile=self.user.profile, is_deleted=True,
                                         **self.address_data)
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        response = self.client.get(reverse('orders:checkout'))
        self.assertNotContains(response, f'id="address-{address.id}"')

        response = self.client.post(reverse('orders:checkout'), {'address': address.id})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_an_address_of_someone_else_is_refused(self):
        other = User.objects.create_user(phone_number='09120000009', password='secret1234')
        address = Address.objects.create(profile=other.profile, **self.address_data)
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        response = self.client.post(reverse('orders:checkout'), {'address': address.id})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_a_nonsense_address_id_does_not_crash(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        response = self.client.post(reverse('orders:checkout'), {'address': 'not-a-number'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_resubmitting_the_same_checkout_does_not_order_twice(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        token = self.client.get(reverse('orders:checkout')).context['checkout_token']
        payload = dict(self.address_data, checkout_token=token)

        first = self.client.post(reverse('orders:checkout'), payload)
        second = self.client.post(reverse('orders:checkout'), payload)

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(first.url, second.url)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 4)

    def test_checkout_without_an_address_does_not_create_an_order(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        response = self.client.post(reverse('orders:checkout'), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_another_customer_cannot_open_the_order(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        self.client.post(reverse('orders:checkout'), self.address_data)
        order = Order.objects.get()

        other = User.objects.create_user(phone_number='09120000001', password='secret1234')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('orders:order_success', args=[order.pk])).status_code, 404)

    def test_stock_lost_after_adding_blocks_the_order(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 4})
        Item.objects.filter(pk=self.item.pk).update(stock=1)

        response = self.client.post(reverse('orders:checkout'), self.address_data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 1)

    def test_checkout_needs_a_login(self):
        self.client.logout()
        response = self.client.get(reverse('orders:checkout'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)


class TrackingTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.force_login(self.user)
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 2})
        self.client.post(reverse('orders:checkout'), ADDRESS)
        self.order = Order.objects.get()
        pay(self.client, self.order)

    def test_placing_and_paying_writes_the_tracking_events(self):
        self.assertEqual([event.status for event in self.order.events.all()],
                         [Order.AWAITING_PAYMENT, 'new'])

    def test_tracking_page_shows_the_steps_and_the_items(self):
        response = self.client.get(reverse('orders:order_detail', args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Brush')
        self.assertContains(response, 'Valiasr Ave')
        steps = response.context['order'].tracking_steps()
        self.assertEqual([step['status'] for step in steps],
                         [Order.AWAITING_PAYMENT, 'new', 'pending', 'accepted', 'delivered'])
        # Paid, so the first two steps are behind it.
        self.assertEqual([step['done'] for step in steps],
                         [True, True, False, False, False])

    def test_steps_fill_up_as_the_order_moves(self):
        self.order.log('accepted', 'Packed')
        steps = Order.objects.get(pk=self.order.pk).tracking_steps()
        self.assertEqual([step['done'] for step in steps], [True, True, True, True, False])

    def test_a_canceled_order_only_keeps_what_really_happened(self):
        self.order.log('canceled', 'Changed my mind')
        steps = Order.objects.get(pk=self.order.pk).tracking_steps()
        self.assertEqual([step['done'] for step in steps],
                         [True, True, False, False, False])

    def test_the_order_history_tab_lists_the_order(self):
        response = self.client.get(reverse('account_profile'))
        self.assertContains(response, f'Order #{self.order.pk}')
        self.assertContains(response, reverse('orders:order_detail', args=[self.order.pk]))

    def test_canceling_gives_the_stock_back(self):
        response = self.client.post(reverse('orders:order_cancel', args=[self.order.pk]))
        self.assertRedirects(response, reverse('orders:order_detail', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.status, 'canceled')
        self.assertEqual(self.item.stock, 5)

    def test_canceling_drops_the_work_that_was_still_queued(self):
        self.assertTrue(self.order.jobs.filter(status=OrderJob.QUEUED).exists())
        self.client.post(reverse('orders:order_cancel', args=[self.order.pk]))
        self.assertFalse(self.order.jobs.filter(status=OrderJob.QUEUED).exists())

    def test_a_delivered_order_cannot_be_canceled_twice(self):
        self.order.log('delivered', 'Handed over')
        self.client.post(reverse('orders:order_cancel', args=[self.order.pk]))
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assertEqual(self.item.stock, 3)

    def test_tracking_is_private_to_its_customer(self):
        other = User.objects.create_user(phone_number='09120000001', password='secret1234')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('orders:order_detail', args=[self.order.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('orders:order_cancel', args=[self.order.pk])).status_code, 404)


class QueueTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234',
                                             email='customer@example.com')
        self.client.force_login(self.user)

    def place_order(self, paid=True):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        self.client.post(reverse('orders:checkout'), ADDRESS)
        order = Order.objects.get()
        if paid:
            pay(self.client, order)
        return order

    def test_checkout_only_queues_the_deadline_that_frees_the_stock(self):
        order = self.place_order(paid=False)
        self.assertEqual([job.kind for job in order.jobs.all()], ['expire_unpaid_order'])
        self.assertGreater(order.jobs.get().run_at, timezone.now())

    def test_paying_queues_the_follow_up_work_instead_of_doing_it(self):
        order = self.place_order()
        self.assertEqual(sorted(job.kind for job in order.jobs.all()),
                         ['confirm_order', 'notify_customer'])
        self.assertEqual({job.status for job in order.jobs.all()}, {OrderJob.QUEUED})
        self.assertEqual(len(mail.outbox), 0)  # nothing slow happened in the request

    def test_the_worker_confirms_and_notifies(self):
        order = self.place_order()
        done, failed = queue.process_jobs()

        self.assertEqual((done, failed), (2, 0))
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertTrue(order.events.filter(status='pending').exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(order.pk), mail.outbox[0].subject)
        self.assertEqual({job.status for job in order.jobs.all()}, {OrderJob.DONE})

    def test_a_failing_job_is_retried_later_and_the_order_survives(self):
        order = self.place_order()
        order.jobs.exclude(kind='notify_customer').delete()

        with mock.patch('orders.queue.send_mail', side_effect=OSError('smtp down')):
            done, failed = queue.process_jobs()

        self.assertEqual((done, failed), (0, 1))
        job = order.jobs.get()
        self.assertEqual(job.status, OrderJob.QUEUED)
        self.assertEqual(job.attempts, 1)
        self.assertGreater(job.run_at, timezone.now())
        self.assertIn('smtp down', job.last_error)

    def test_a_job_gives_up_after_its_last_attempt(self):
        order = self.place_order()
        order.jobs.exclude(kind='notify_customer').delete()
        job = order.jobs.get()
        OrderJob.objects.filter(pk=job.pk).update(attempts=job.max_attempts - 1)

        with mock.patch('orders.queue.send_mail', side_effect=OSError('smtp down')):
            queue.process_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, OrderJob.FAILED)

    def test_jobs_that_are_not_due_yet_are_left_alone(self):
        order = self.place_order()
        order.jobs.update(run_at=timezone.now() + timezone.timedelta(hours=1))
        self.assertEqual(queue.process_jobs(), (0, 0))
        self.assertEqual(order.jobs.filter(status=OrderJob.QUEUED).count(), 2)

    def test_a_job_is_only_handed_out_once(self):
        self.place_order()
        first = queue.claim_job()
        second = queue.claim_job()
        self.assertIsNotNone(first)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.status, OrderJob.RUNNING)

    def test_the_worker_command_runs(self):
        from io import StringIO

        from django.core.management import call_command
        self.place_order()
        out = StringIO()
        call_command('process_order_jobs', stdout=out)
        self.assertIn('processed 2 job(s)', out.getvalue())
        self.assertFalse(OrderJob.objects.filter(status=OrderJob.QUEUED).exists())

    def test_an_unknown_job_kind_is_refused_at_enqueue_time(self):
        order = self.place_order()
        with self.assertRaises(ValueError):
            queue.enqueue(order, 'does_not_exist')
