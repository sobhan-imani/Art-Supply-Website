"""The picture an Item actually shows, with a fallback for the ones that don't have one.

Item.picture1 has always been a required field, with a `default` that names a
file (item-images/default.jpg) nobody ever shipped: for every product created
without a real upload - the fixtures, the tests, a script - that name resolves
to a URL that 404s. This gives every consumer (templates and the API alike)
one place to ask "what should this actually show?" instead of trusting the
field's default.
"""

from django.templatetags.static import static

PLACEHOLDER = 'img/product-placeholder.jpg'


def item_picture_url(item, field='picture1'):
    """The item's own picture if the file is really there, a placeholder otherwise."""
    picture = getattr(item, field, None)
    name = getattr(picture, 'name', '') if picture else ''
    if name:
        try:
            if picture.storage.exists(name):
                return picture.url
        except (OSError, ValueError):
            pass  # a storage backend that can't answer is treated as "no file"
    return static(PLACEHOLDER)
