import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.templatetags.static import static
from django.test import TestCase, override_settings
from django.urls import reverse

from .images import PLACEHOLDER, item_picture_url
from .models import Category, Item

User = get_user_model()


class ProductPageTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(category_name='paint')
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=4,
                                        category=self.category, discount=25)

    def test_detail_page_renders_everything_it_promises(self):
        response = self.client.get(reverse('product-detail', args=[self.item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Brush')
        self.assertContains(response, '$7.50')  # 25% off
        self.assertContains(response, reverse('orders:cart_add', args=[self.item.id]))

    def test_anonymous_visitors_are_pointed_at_the_login_for_the_wishlist(self):
        response = self.client.get(reverse('product-detail', args=[self.item.id]))
        self.assertContains(response, f"{reverse('account_login')}?next=")
        self.assertNotContains(response, 'id="wishlist"')

    def test_logged_in_visitors_get_the_wishlist_button(self):
        User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.login(username='09120000000', password='secret1234')
        response = self.client.get(reverse('product-detail', args=[self.item.id]))
        self.assertContains(response, 'id="wishlist"')
        self.assertContains(response, reverse('wishlist', args=[self.item.id]))
        self.assertFalse(response.context['is_in_wishlist'])

    def test_an_out_of_stock_item_cannot_be_added(self):
        self.item.stock = 0
        self.item.save()
        response = self.client.get(reverse('product-detail', args=[self.item.id]))
        self.assertContains(response, 'Out of stock')
        self.assertNotContains(response, reverse('orders:cart_add', args=[self.item.id]))

    def test_search_by_name_and_description(self):
        Item.objects.create(name='Canvas', price=Decimal('5.00'), stock=1,
                            descriptions='cotton, primed')
        response = self.client.get(reverse('products-list'), {'q': 'brush'})
        self.assertEqual([item.name for item in response.context['products']], ['Brush'])
        response = self.client.get(reverse('products-list'), {'q': 'cotton'})
        self.assertEqual([item.name for item in response.context['products']], ['Canvas'])

    def test_sorting_by_price(self):
        Item.objects.create(name='Canvas', price=Decimal('5.00'), stock=1)
        cheap_first = self.client.get(reverse('products-list'), {'sort': 'price'})
        self.assertEqual([i.name for i in cheap_first.context['products']], ['Canvas', 'Brush'])
        dear_first = self.client.get(reverse('products-list'), {'sort': '-price'})
        self.assertEqual([i.name for i in dear_first.context['products']], ['Brush', 'Canvas'])

    def test_a_nonsense_sort_falls_back_instead_of_failing(self):
        response = self.client.get(reverse('products-list'), {'sort': 'price; drop table'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['sort'], 'new')

    def test_a_parent_category_includes_its_children(self):
        child = Category.objects.create(category_name='acrylic', sub_category=self.category)
        Item.objects.create(name='Acrylic set', price=Decimal('8.00'), stock=1, category=child)
        Item.objects.create(name='Canvas', price=Decimal('5.00'), stock=1)

        response = self.client.get(reverse('products-list'), {'category': 'paint'})
        names = sorted(item.name for item in response.context['products'])
        self.assertEqual(names, ['Acrylic set', 'Brush'])

    def test_the_discount_filter(self):
        Item.objects.create(name='Canvas', price=Decimal('5.00'), stock=1)
        response = self.client.get(reverse('products-list'), {'discount': '1'})
        self.assertEqual([item.name for item in response.context['products']], ['Brush'])

    def test_paging_keeps_the_filters(self):
        # Page links used to be a bare ?page=N, which reset the filters.
        for index in range(8):
            Item.objects.create(name=f'Paint {index}', price=Decimal('3.00'), stock=1,
                                category=self.category, discount=10)
        response = self.client.get(reverse('products-list'), {'category': 'paint', 'sort': 'name'})
        self.assertContains(response, 'category=paint&amp;sort=name&amp;page=2')

        second = self.client.get(reverse('products-list'),
                                 {'category': 'paint', 'sort': 'name', 'page': 2})
        self.assertEqual(second.context['category'], 'paint')
        self.assertEqual(second.context['sort'], 'name')

    def test_active_filters_can_be_cleared_one_by_one(self):
        response = self.client.get(reverse('products-list'), {'category': 'paint', 'q': 'br'})
        self.assertContains(response, 'q=br')          # chip that drops the category
        self.assertContains(response, 'category=paint')  # chip that drops the search

    def test_list_page_and_category_filter(self):
        Item.objects.create(name='Canvas', price=Decimal('5.00'), stock=1)
        response = self.client.get(reverse('products-list'))
        self.assertContains(response, 'Brush')
        self.assertContains(response, 'Canvas')

        response = self.client.get(reverse('products-list'), {'category': 'paint'})
        self.assertContains(response, 'Brush')
        self.assertNotContains(response, 'Canvas')


class WishlistApiTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=4)
        self.user = User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.url = reverse('wishlist', args=[self.item.id])

    def test_the_session_login_is_enough_to_toggle_the_wishlist(self):
        # This is what the button on the product page does: no JWT in sight.
        self.client.login(username='09120000000', password='secret1234')

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json()['wishlist']], [self.item.id])
        self.assertTrue(self.user.profile.wishlist.filter(pk=self.item.pk).exists())

        response = self.client.post(self.url)
        self.assertEqual(response.json()['wishlist'], [])
        self.assertFalse(self.user.profile.wishlist.exists())

    def test_a_jwt_works_too(self):
        token = self.client.post(reverse('token_obtain_pair'), {
            'phone_number': '09120000000', 'password': 'secret1234'}).json()['access']
        response = self.client.post(self.url, HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(response.status_code, 200)

    def test_anonymous_visitors_are_refused(self):
        # 401 from the JWT layer, 403 from the session layer: either is a refusal.
        self.assertIn(self.client.post(self.url).status_code, (401, 403))

    def test_an_unknown_item_is_a_404_not_a_crash(self):
        self.client.login(username='09120000000', password='secret1234')
        self.assertEqual(self.client.post(reverse('wishlist', args=[9999])).status_code, 404)

    def test_the_toggle_answers_with_the_wishlist_alone(self):
        # It used to return every order and address of the customer as well.
        self.client.login(username='09120000000', password='secret1234')
        payload = self.client.post(self.url).json()
        self.assertEqual(list(payload), ['wishlist'])

    def test_the_profile_endpoint_serializes_orders(self):
        # ProfileSerializer nests the order rows, which used to blow up.
        self.client.login(username='09120000000', password='secret1234')
        self.client.post(reverse('orders:cart_add', args=[self.item.id]), {'quantity': 1})
        self.client.post(reverse('orders:checkout'), {
            'country': 'Iran', 'city': 'Tehran', 'street': 'Valiasr Ave', 'postal_code': '123'})

        response = self.client.get(reverse('api_profile'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['orders']), 1)
        self.assertEqual(payload['orders'][0]['items'][0]['quantity'], 1)
        self.assertEqual(len(payload['addresses']), 1)

    def test_the_profile_endpoint_needs_a_login(self):
        self.assertIn(self.client.get(reverse('api_profile')).status_code, (401, 403))


class ProductImageFallbackTests(TestCase):
    """Item.picture1 has always had a default naming a file nobody ships, so
    every item created without a real upload used to serialize or render a
    URL that 404s.
    """

    def setUp(self):
        # A real upload writes to MEDIA_ROOT; keep that out of the project's own
        # media/ directory instead of leaving files behind after every test run.
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)

        self.item = Item.objects.create(name='Brush', price=Decimal('10.00'), stock=4)

    def test_an_item_with_no_real_file_gets_the_placeholder(self):
        self.assertEqual(item_picture_url(self.item), static(PLACEHOLDER))

    def test_an_item_with_a_real_file_keeps_its_own_picture(self):
        self.item.picture1 = SimpleUploadedFile('brush.jpg', b'not a real jpeg, just bytes')
        self.item.save()
        url = item_picture_url(self.item)
        self.assertNotEqual(url, static(PLACEHOLDER))
        self.assertIn('brush', url)

    def test_the_product_list_shows_the_placeholder_not_a_broken_image(self):
        response = self.client.get(reverse('products-list'))
        self.assertContains(response, static(PLACEHOLDER))

    def test_the_product_detail_page_shows_the_placeholder(self):
        response = self.client.get(reverse('product-detail', args=[self.item.id]))
        self.assertContains(response, static(PLACEHOLDER))

    def test_the_api_serves_the_same_placeholder(self):
        User.objects.create_user(phone_number='09120000000', password='secret1234')
        self.client.login(username='09120000000', password='secret1234')
        response = self.client.post(reverse('wishlist', args=[self.item.id]))
        self.assertIn(static(PLACEHOLDER), response.json()['wishlist'][0]['picture1'])
