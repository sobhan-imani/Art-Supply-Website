from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from customers.models import Address, Profile
from orders.models import Order, OrderItem
from products.models import Category, Item

User = get_user_model()


class SoftDeleteTests(TestCase):
    """BaseModel.delete() withdraws a row instead of destroying it."""

    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)

    def test_delete_only_sets_the_flag(self):
        self.item.delete()
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_deleted)

    def test_the_default_manager_hides_deleted_rows(self):
        self.item.delete()
        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())
        self.assertTrue(Item.all_objects.filter(pk=self.item.pk).exists())
        # objects.deleted() is the deliberate escape hatch for listing what was
        # withdrawn, the same api the project had before.
        self.assertEqual([row.pk for row in Item.objects.deleted()], [self.item.pk])
        self.assertEqual([row.pk for row in Item.all_objects.deleted()], [self.item.pk])

    def test_the_manager_django_follows_relations_with_is_the_filtered_one(self):
        # If _default_manager were the unfiltered one, deleted rows would come
        # back through every related manager and every generic view.
        for model in (Item, Category, Address, Profile, Order, OrderItem):
            with self.subTest(model=model.__name__):
                self.assertEqual(model._default_manager.name, 'objects')
                self.assertFalse(model._default_manager.with_deleted().query.where)

    def test_queryset_delete_is_soft_too(self):
        Item.objects.filter(pk=self.item.pk).delete()
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_deleted)

    def test_hard_delete_is_available_when_it_is_really_meant(self):
        pk = self.item.pk
        self.item.delete(hard=True)
        self.assertFalse(Item.all_objects.filter(pk=pk).exists())

        other = Item.objects.create(name='Canvas', price=Decimal('5.00'), stock=1)
        Item.objects.filter(pk=other.pk).delete(hard=True)
        self.assertFalse(Item.all_objects.filter(pk=other.pk).exists())

    def test_restore(self):
        self.item.delete()
        self.item.restore()
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())

    def test_managers_of_products_respect_the_flag(self):
        Item.objects.create(name='Discounted', price=Decimal('10.00'), stock=2, discount=20)
        self.item.delete()
        self.assertNotIn(self.item, Item.objects.is_available())
        self.assertNotIn(self.item, Item.objects.last_items(10))
        self.assertNotIn(self.item, Item.objects.is_discounted())


class WithdrawnProductTests(TestCase):
    """A withdrawn product leaves the shop but does not break what it touched."""

    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.force_login(self.user)
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 2})
        self.client.post(reverse('orders:checkout'), {
            'country': 'Iran', 'city': 'Tehran', 'street': 'Valiasr Ave', 'postal_code': '123'})
        self.order = Order.objects.get()

    def test_it_disappears_from_the_shop(self):
        self.item.delete()
        # Look for the link a product card renders, not for the name: the name
        # also shows up in a leftover "added to your cart" message.
        link = reverse('product-detail', args=[self.item.pk])
        response = self.client.get(reverse('products-list'))
        self.assertNotContains(response, link)
        self.assertEqual(list(response.context['products']), [])
        self.assertNotContains(self.client.get(reverse('home')), link)
        self.assertEqual(self.client.get(link).status_code, 404)

    def test_orders_that_contain_it_keep_working(self):
        self.item.delete()
        row = self.order.order_items.first()
        self.assertEqual(row.item.name, 'Brush')  # the order keeps its own record

        for url in (reverse('orders:order_detail', args=[self.order.pk]),
                    reverse('orders:order_success', args=[self.order.pk]),
                    reverse('account_profile')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Brush')

    def test_it_drops_out_of_a_cart_that_still_holds_it(self):
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        self.item.delete()
        response = self.client.get(reverse('products-list'))
        self.assertEqual(len(response.context['cart']), 0)

    def test_a_withdrawn_product_cannot_be_added_to_a_cart(self):
        self.item.delete()
        response = self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        self.assertEqual(response.status_code, 404)


class DeletedAddressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.address = Address.objects.create(profile=self.user.profile, country='Iran',
                                              city='Tehran', street='Valiasr Ave',
                                              postal_code='123')

    def test_a_removed_address_stays_on_the_orders_that_used_it(self):
        order = Order.objects.create(profile=self.user.profile, address=self.address,
                                     price=Decimal('10.00'))
        self.address.delete()

        self.assertFalse(self.user.profile.addresses.exists())          # gone from the profile
        self.assertEqual(Order.objects.get(pk=order.pk).address.street, 'Valiasr Ave')
