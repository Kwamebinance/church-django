import calendar
from django import template
register = template.Library()


@register.filter
def month_name(month_number):
    try:
        return calendar.month_abbr[int(month_number)]
    except (ValueError, IndexError, TypeError):
        return ""
