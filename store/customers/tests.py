from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .models import Address

User = get_user_model()


class ProfileSignalTests(TestCase):
    def test_every_new_user_gets_a_profile(self):
        # The receiver is registered by an import in CustomersConfig.ready(),
        # which is easy to tidy away by accident: without it every page that
        # touches user.profile breaks.
        user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.assertIsNotNone(user.profile)
        self.assertEqual(user.profile.user, user)

    def test_a_superuser_gets_one_too(self):
        staff = User.objects.create_superuser(phone_number='09120000001', password='secret1234')
        self.assertIsNotNone(staff.profile)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.force_login(self.user)

    def test_profile_shows_every_tab(self):
        response = self.client.get(reverse('account_profile'))
        self.assertEqual(response.status_code, 200)
        for tab in ['id="list-home"', 'id="Wishlist"', 'id="list-orders"', 'id="Address"']:
            self.assertContains(response, tab)

    def test_saving_details_confirms_with_a_message(self):
        response = self.client.post(reverse('account_profile'), {
            'phone_number': '09120000000', 'first_name': 'Sobhan',
            'last_name': 'Imani', 'email': 'sobhan@example.com'}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Sobhan')
        self.assertIn('saved', ' '.join(str(m) for m in get_messages(response.wsgi_request)))

    def test_invalid_details_are_reported_on_the_page(self):
        response = self.client.post(reverse('account_profile'), {
            'phone_number': '', 'first_name': 'Sobhan', 'last_name': '', 'email': 'nope'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a valid email address')
        self.assertContains(response, 'is-invalid')


class AddressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.force_login(self.user)
        self.data = {'country': 'Iran', 'city': 'Tehran', 'district': '', 'street': 'Valiasr Ave',
                     'alley': '', 'postal_code': '1234567890'}

    def create(self):
        return Address.objects.create(profile=self.user.profile, country='Iran', city='Tehran',
                                      street='Valiasr Ave', postal_code='1234567890')

    def test_add_address_from_the_profile_page(self):
        response = self.client.post(reverse('address_create'), self.data)
        self.assertRedirects(response, f"{reverse('account_profile')}#Address",
                             target_status_code=200, fetch_redirect_response=False)
        address = Address.objects.get()
        self.assertEqual(address.profile, self.user.profile)

    def test_invalid_address_is_reported(self):
        response = self.client.post(reverse('address_create'), dict(self.data, city=''))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Address.objects.exists())
        self.assertContains(response, 'This field is required')

    def test_edit_address(self):
        address = self.create()
        self.client.post(reverse('address_update', args=[address.id]), dict(self.data, city='Shiraz'))
        address.refresh_from_db()
        self.assertEqual(address.city, 'Shiraz')

    def test_remove_is_a_soft_delete_so_orders_keep_their_address(self):
        address = self.create()
        self.client.post(reverse('address_delete', args=[address.id]))
        address.refresh_from_db()
        self.assertTrue(address.is_deleted)
        response = self.client.get(reverse('account_profile'))
        self.assertNotContains(response, 'Valiasr Ave')

    def test_another_customer_cannot_touch_the_address(self):
        address = self.create()
        other = User.objects.create_user(phone_number='09120000001', password='secret1234')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('address_update', args=[address.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse('address_delete', args=[address.id])).status_code, 404)

    def test_address_forms_need_a_login(self):
        self.client.logout()
        response = self.client.get(reverse('address_create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)


class AuthMessageTests(TestCase):
    def test_signup_success_message_reaches_the_login_page(self):
        response = self.client.post(reverse('account_signup'), {
            'phone_number': '09120000000', 'first_name': 'Sobhan', 'last_name': 'Imani',
            'email': 'sobhan@example.com', 'password1': 'sup3r-secret-pw',
            'password2': 'sup3r-secret-pw'}, follow=True)
        self.assertRedirects(response, reverse('account_login'))
        self.assertContains(response, 'Account created successfully')
        self.assertTrue(User.objects.filter(phone_number='09120000000').exists())

    def test_signup_errors_are_shown(self):
        response = self.client.post(reverse('account_signup'), {
            'phone_number': '09120000000', 'email': 'sobhan@example.com',
            'password1': 'sup3r-secret-pw', 'password2': 'different-pw'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The two password fields didn’t match.')
        self.assertFalse(User.objects.exists())

    def test_wrong_login_says_so(self):
        User.objects.create_user(phone_number='09120000000', password='secret1234')
        response = self.client.post(reverse('account_login'), {
            'username': '09120000000', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Wrong phone number or password')
        self.assertContains(response, 'is-invalid')

    def test_login_honours_the_next_parameter(self):
        user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        response = self.client.post(f"{reverse('account_login')}?next={reverse('account_profile')}", {
            'username': user.phone_number, 'password': 'secret1234'})
        self.assertRedirects(response, reverse('account_profile'))
