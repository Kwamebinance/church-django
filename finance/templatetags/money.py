"""
Reusable money display: base-currency figure with the ESPEES equivalent beneath.

The ESPEES line behaves in three ways:
  - frozen value present  -> show it exactly:        "≈ 6,148.20 ESPEES"
  - frozen null + church given + a current rate ->   "≈ 6,148.20 ESPEES (today's rate)"  (live estimate)
  - no rate at all                              ->   "ESPEES —"

Usage in templates:
    {% load money %}
    {% money r.base_amount r.church.default_currency r.espees_amount r.church %}
The trailing church arg is optional but enables the live estimate fallback.
"""
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def money(base_amount, base_currency, espees_amount=None, church=None):
    """Render base amount as the main figure with ESPEES equivalent beneath.
    If the frozen espees_amount is null but a church is supplied and a current
    ESPEES rate exists, show a live estimate marked '(today's rate)'."""
    if base_amount is None:
        main = format_html('<span class="money-main">—</span>')
    else:
        main = format_html('<span class="money-main">{} {}</span>',
                           _fmt(base_amount), base_currency)
    # no redundant ESPEES line if the base currency already IS ESPEES
    if base_currency == "ESPEES":
        return format_html('<span class="money">{}</span>', main)

    if espees_amount is not None:
        sub = format_html('<span class="money-espees">≈ {} ESPEES</span>', _fmt(espees_amount))
    else:
        # try a live estimate from the current rate
        live = _live_espees(base_amount, church)
        if live is not None:
            sub = format_html('<span class="money-espees">≈ {} ESPEES '
                              '<span class="money-est">(today\'s rate)</span></span>', _fmt(live))
        else:
            sub = format_html('<span class="money-espees">ESPEES —</span>')
    return format_html('<span class="money">{}<br>{}</span>', main, sub)


def _live_espees(base_amount, church):
    """Compute a current-rate ESPEES estimate, or None if not possible."""
    if church is None or base_amount is None:
        return None
    try:
        from finance.services import convert_to_espees
        return convert_to_espees(base_amount, church)
    except Exception:  # noqa: BLE001 - never break rendering over an estimate
        return None


def _fmt(value):
    """Thousands-separated, 2dp, deterministic (no locale — SSR-safe)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{n:,.2f}"


@register.filter
def amount(value):
    """Format a number with thousands separators + 2dp, for inline use."""
    return _fmt(value)


@register.filter
def rate_display(value):
    """Display an exchange rate at 2dp for clean everyday rates, but fall back to
    full precision when 2dp would round away real value (e.g. small rates like
    0.0098 → would wrongly show 0.01). Trailing zeros trimmed on the full form.
    The STORED value is always full precision; this only affects display."""
    from decimal import Decimal, InvalidOperation
    if value is None:
        return "—"
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    two = d.quantize(Decimal("0.01"))
    # if rounding to 2dp changes the value meaningfully, show full precision
    if two != d:
        # trim trailing zeros but keep at least 2dp
        full = d.normalize()
        s = format(full, "f")
        if "." in s:
            int_part, frac = s.split(".")
            frac = frac.ljust(2, "0")
            return f"{int_part}.{frac}"
        return f"{s}.00"
    return f"{two:.2f}"
