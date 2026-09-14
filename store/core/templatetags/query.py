from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """The current query string with some parameters changed or dropped.

    Pagination links used to be plain `?page=2`, which threw away whatever the
    customer had filtered or sorted by. Usage:

        <a href="?{% query_replace page=page_obj.next_page_number %}">
        <a href="?{% query_replace category=None page=None %}">
    """
    request = context.get('request')
    query = request.GET.copy() if request else template.Variable('_').literal
    for key, value in kwargs.items():
        if value in (None, '', False):
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()
