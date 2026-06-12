"""Template tags for the breadcrumb trail (see accounts/navigation.py)."""
from urllib.parse import urlencode
from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.html import escape

from accounts.navigation import (decode_trail, append_to_trail, encode_trail,
                                  safe_internal_path)

register = template.Library()


def _strip_trail_param(full_path):
    """Remove an existing ?trail= (or &trail=) token from a path so stored trail
    entries don't nest encoded trails inside each other."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl
    parts = urlsplit(full_path)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "trail"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


@register.simple_tag(takes_context=True)
def trail_link(context, url, label):
    """Build a link to `url` that carries the trail with the CURRENT page
    appended (so 'back' from the destination returns here, preserving the
    current page's query string — e.g. active list filters). Use on drill-down
    links: <a href="{% trail_link some_url 'This Page' %}">…</a>."""
    request = context["request"]
    current = request.get_full_path()  # includes query (filters, page, etc.)
    # but strip any existing ?trail= from what we store, to avoid nesting tokens
    trail = decode_trail(request)
    current = _strip_trail_param(current)
    new_trail = append_to_trail(trail, current, label)
    token = encode_trail(new_trail)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode({'trail': token})}"


@register.simple_tag(takes_context=True)
def crumbs(context, home_url, home_label, current_label):
    """Render the breadcrumb: home › ...trail... › current (current not linked).
    home_url/home_label are the module default (trusted). current_label names
    this page. Trail hops are validated + clickable, carrying their own sub-trail
    so clicking a crumb returns with the correct shortened trail."""
    request = context["request"]
    trail = decode_trail(request)
    # safety net: drop any trail hop that points at the home URL itself, so the
    # home crumb is never duplicated (e.g. a same-module drill-down link that
    # also added the module home to the trail).
    from urllib.parse import urlsplit
    home_path = urlsplit(home_url).path
    trail = [h for h in trail if urlsplit(h["url"]).path != home_path]
    parts = []
    # home crumb
    parts.append(f'<a href="{escape(home_url)}">{escape(home_label)}</a>')
    # intermediate crumbs (each clickable, carrying the trail up to itself)
    accumulated = []
    for hop in trail:
        accumulated = append_to_trail(accumulated, hop["url"], hop["label"])
        # link to the hop carrying the trail truncated up to (not including) it
        prior = accumulated[:-1]
        href = hop["url"]
        if prior:
            sep = "&" if "?" in href else "?"
            href = f"{href}{sep}{urlencode({'trail': encode_trail(prior)})}"
        parts.append(f'<a href="{escape(href)}">{escape(hop["label"])}</a>')
    # current (not a link)
    parts.append(f'<span class="crumb-current">{escape(current_label)}</span>')
    sep = '<span class="crumb-sep">›</span>'
    return mark_safe('<nav class="crumbs">' + sep.join(parts) + '</nav>')


@register.simple_tag(takes_context=True)
def back_url(context, fallback):
    """A single 'back' href: last trail hop carrying its remaining trail, else
    the fallback module-default URL."""
    request = context["request"]
    trail = decode_trail(request)
    if not trail:
        return fallback
    last = trail[-1]
    prior = trail[:-1]
    href = last["url"]
    if prior:
        sep = "&" if "?" in href else "?"
        href = f"{href}{sep}{urlencode({'trail': encode_trail(prior)})}"
    return href
