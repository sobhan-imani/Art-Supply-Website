# The address form lives with the Address model in the customers app; checkout
# and the profile page must stay in sync, so there is only one of them.
from customers.forms import AddressForm

__all__ = ['AddressForm']
