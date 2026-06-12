from django import template
register = template.Library()


@register.filter
def get_item(d, key):
    """Look up a dict value by a variable key in templates."""
    try:
        return d.get(key)
    except AttributeError:
        return None
