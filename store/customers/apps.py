from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CustomersConfig(AppConfig):
    name = 'customers'
    # AppConfig takes verbose_name directly: a nested Meta does nothing here.
    verbose_name = _('Customers')

    def ready(self):
        # Importing for the side effect of registering the receivers: this is
        # what creates a Profile for every new user, so it must not be tidied
        # away as an unused import.
        import customers.signals  # noqa: F401
