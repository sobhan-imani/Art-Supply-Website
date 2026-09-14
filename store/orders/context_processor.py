from .cart import Cart


def cart(request):
    """Give every template the visitor's cart for the navbar cart sidebar.

    Building it is cheap: no query is made until a template iterates it or
    asks for its length.
    """
    return {'cart': Cart(request)}
