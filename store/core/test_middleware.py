from unittest import mock

from django.test import RequestFactory, TestCase, override_settings

from .middleware import RestrictCountryIpMiddleware


def make_request(path='/'):
    request = RequestFactory().get(path, REMOTE_ADDR='1.2.3.4')
    request.session = {}
    return request


def ok(request):
    from django.http import HttpResponse
    return HttpResponse('ok')


class RestrictCountryTests(TestCase):
    def middleware(self):
        return RestrictCountryIpMiddleware(ok)

    @override_settings(RESTRICTED_COUNTRY_CODES=[])
    def test_off_when_no_country_is_listed(self):
        with mock.patch('core.middleware.get_ip_info') as lookup:
            response = self.middleware()(make_request())
        self.assertEqual(response.status_code, 200)
        lookup.assert_not_called()  # not even a lookup, let alone a blocking one

    @override_settings(RESTRICTED_COUNTRY_CODES=['US'])
    def test_blocks_a_listed_country(self):
        with mock.patch('core.middleware.get_ip_info', return_value={'countryCode': 'US'}):
            response = self.middleware()(make_request())
        self.assertEqual(response.status_code, 403)

    @override_settings(RESTRICTED_COUNTRY_CODES=['us'])
    def test_the_comparison_ignores_case(self):
        with mock.patch('core.middleware.get_ip_info', return_value={'countryCode': 'US'}):
            self.assertEqual(self.middleware()(make_request()).status_code, 403)

    @override_settings(RESTRICTED_COUNTRY_CODES=['US'])
    def test_lets_everyone_else_through(self):
        with mock.patch('core.middleware.get_ip_info', return_value={'countryCode': 'IR'}):
            self.assertEqual(self.middleware()(make_request()).status_code, 200)

    @override_settings(RESTRICTED_COUNTRY_CODES=['US'])
    def test_fails_open_when_the_service_is_down(self):
        # An unreachable geo service must not lock the shop.
        with mock.patch('core.middleware.get_ip_info', return_value={}):
            self.assertEqual(self.middleware()(make_request()).status_code, 200)

    @override_settings(RESTRICTED_COUNTRY_CODES=['US'])
    def test_one_lookup_per_visitor(self):
        request = make_request()
        with mock.patch('core.middleware.get_ip_info', return_value={'countryCode': 'IR'}) as lookup:
            middleware = self.middleware()
            middleware(request)
            middleware(request)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(request.session['countryCode'], 'IR')


class IpLookupTests(TestCase):
    def test_a_failing_lookup_returns_nothing_instead_of_raising(self):
        import requests

        from .utils import get_ip_info
        with mock.patch('core.utils.requests.get', side_effect=requests.Timeout('too slow')):
            self.assertEqual(get_ip_info('1.2.3.4'), {})

    def test_it_asks_over_https_with_a_timeout(self):
        from .utils import get_ip_info
        with mock.patch('core.utils.requests.get') as get:
            get.return_value.json.return_value = {'countryCode': 'IR'}
            self.assertEqual(get_ip_info('1.2.3.4'), {'countryCode': 'IR'})

        url, kwargs = get.call_args[0][0], get.call_args[1]
        self.assertTrue(url.startswith('https://'))
        self.assertIn('timeout', kwargs)

    def test_no_address_means_no_request(self):
        from .utils import get_ip_info
        with mock.patch('core.utils.requests.get') as get:
            self.assertEqual(get_ip_info(''), {})
        get.assert_not_called()
