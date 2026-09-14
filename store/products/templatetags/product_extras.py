from django import template

from products.images import item_picture_url

register = template.Library()


@register.filter
def product_image(item):
    """The URL to use for an item's main picture, placeholder included.

    Usage: `<img src="{{ item|product_image }}">`
    """
    return item_picture_url(item, 'picture1')
