from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from products.models import Item

User = get_user_model()


class SoftDeleteAdminTests(TestCase):
    """Staff must still be able to see and undo a withdrawal."""

    def setUp(self):
        self.staff = User.objects.create_superuser(phone_number='09120000000',
                                                   password='secret1234')
        self.client.force_login(self.staff)
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=5)
        self.changelist = reverse('admin:products_item_changelist')

    def test_withdrawn_items_are_still_listed(self):
        self.item.delete()
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Brush')

    def test_the_admin_delete_button_withdraws_instead_of_destroying(self):
        response = self.client.post(
            reverse('admin:products_item_delete', args=[self.item.pk]), {'post': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_deleted)

    def test_the_bulk_actions_withdraw_and_restore(self):
        self.client.post(self.changelist, {'action': 'withdraw_selected',
                                           '_selected_action': [str(self.item.pk)]})
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_deleted)

        self.client.post(self.changelist, {'action': 'restore_selected',
                                           '_selected_action': [str(self.item.pk)]})
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_deleted)

    def test_searching_items_works(self):
        # search_fields used to name a field that does not exist on the model.
        response = self.client.get(self.changelist, {'q': 'Brush'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Brush')

    def test_the_other_soft_delete_changelists_open(self):
        for name in ('products_category', 'customers_profile', 'customers_address',
                     'orders_order', 'orders_orderitem', 'orders_orderevent',
                     'orders_orderjob'):
            with self.subTest(admin=name):
                response = self.client.get(reverse(f'admin:{name}_changelist'))
                self.assertEqual(response.status_code, 200)
