import logging

import requests

logger = logging.getLogger(__name__)

# An unreachable geo service must never hold a request open.
IP_LOOKUP_TIMEOUT = 3
IP_LOOKUP_URL = 'https://ip-api.ir/info/{ip}'


def get_request_ip(request) -> str:
    """The IP the request came from, remembered in the session once resolved."""
    ip = request.session.get('ip', None)
    if not ip:
        x_forward_for = request.META.get('HTTP_X_FORWARDED_FOR', None)
        if x_forward_for:
            ip = x_forward_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
    return ip


def get_ip_info(ip: str) -> dict:
    """Whatever the geo service knows about an address, or {} if it cannot say.

    Never raises: callers decide what to do with an empty answer, and the site
    must stay up when the service is down.
    """
    if not ip:
        return {}
    try:
        response = requests.get(IP_LOOKUP_URL.format(ip=ip), timeout=IP_LOOKUP_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning('could not look up the country of %s: %s', ip, error)
        return {}
