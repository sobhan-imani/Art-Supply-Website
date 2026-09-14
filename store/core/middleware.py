import logging

from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.translation import gettext as _

from .utils import get_ip_info, get_request_ip

logger = logging.getLogger(__name__)


class RestrictCountryIpMiddleware:
    """Turn visitors from certain countries away.

    Off unless RESTRICTED_COUNTRY_CODES is set, and it fails open: when the geo
    service cannot be reached the visitor is let through rather than locked out.
    The answer is cached in the session, so it costs one lookup per visitor.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_restricted(request):
            return HttpResponseForbidden(_('This site is not available in your country.'))
        return self.get_response(request)

    def _is_restricted(self, request) -> bool:
        restricted = [code.upper() for code in self._restricted_countries()]
        if not restricted:
            return False

        code = request.session.get('countryCode')
        if code is None:
            ip = get_request_ip(request)
            code = get_ip_info(ip).get('countryCode') or ''
            # Cache the miss too, so a flaky service is not called on every hit.
            request.session['ip'] = ip
            request.session['countryCode'] = code

        return bool(code) and code.upper() in restricted

    def _restricted_countries(self) -> list:
        return getattr(settings, 'RESTRICTED_COUNTRY_CODES', None) or []
