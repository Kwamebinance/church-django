"""
Currency conversion — the foundation income/expense recording builds on.

convert_to_base(amount, currency, church, as_of) returns (base_amount, rate):
  - if `currency` is the church's base currency, rate is 1 and base == amount.
  - otherwise we find the applicable CurrencySnapshot effective on/before `as_of`,
    searching church-specific first, then zone, then global (church is null),
    and convert. If no rate is found, we return (None, None) so the caller can
    flag the entry rather than silently guess.

Rates are stored directionally as base->quote (1 base = `rate` quote). To convert
an `amount` given in `currency` (the quote) back to base: base = amount / rate.
We also accept the inverse direction (quote->base) if that's how a snapshot was
entered, picking whichever pair matches.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone


TWO_PLACES = Decimal("0.01")


def _q(amount):
    return Decimal(amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def find_rate(church, base_currency, quote_currency, as_of=None):
    """Return a Decimal rate to convert 1 unit of quote_currency into base_currency,
    or None. Searches church-specific snapshots first, then global (church is null).
    """
    from .models import CurrencySnapshot
    if as_of is None:
        as_of = timezone.now()
    if base_currency == quote_currency:
        return Decimal("1")

    # search order: this church, then global (church is null)
    scopes = [{"church": church}, {"church__isnull": True}]
    for scope in scopes:
        qs = CurrencySnapshot.objects.filter(effective_from__lte=as_of, **scope)
        # direct pair base->quote: 1 base = rate quote  => to get base from quote, divide
        direct = qs.filter(base_currency=base_currency, quote_currency=quote_currency
                           ).order_by("-effective_from").first()
        if direct and direct.rate:
            return Decimal("1") / Decimal(direct.rate)
        # inverse pair quote->base: 1 quote = rate base  => multiply
        inverse = qs.filter(base_currency=quote_currency, quote_currency=base_currency
                            ).order_by("-effective_from").first()
        if inverse and inverse.rate:
            return Decimal(inverse.rate)
    return None


def convert_to_base(amount, currency, church, as_of=None):
    """Convert `amount` in `currency` to the church's base (default) currency.
    Returns (base_amount: Decimal|None, exchange_rate: Decimal|None).
    exchange_rate is the multiplier applied: base_amount = amount * exchange_rate.
    """
    base_currency = church.default_currency
    if currency == base_currency:
        return _q(amount), Decimal("1")
    rate = find_rate(church, base_currency, currency, as_of)
    if rate is None:
        return None, None
    base_amount = _q(Decimal(amount) * rate)
    return base_amount, rate


ESPEES = "ESPEES"


def convert_to_espees(base_amount, church, as_of=None):
    """Convert an amount already in the church's base currency into ESPEES,
    using the ESPEES rate effective on/before `as_of`. Returns Decimal or None.
    If the base currency IS ESPEES, returns the amount unchanged."""
    if base_amount is None:
        return None
    base_currency = church.default_currency
    if base_currency == ESPEES:
        return _q(base_amount)
    # we want: how many ESPEES is `base_amount` of base_currency worth?
    # find_rate(church, ESPEES, base_currency) gives ESPEES-per-1-base.
    rate = find_rate(church, ESPEES, base_currency, as_of)
    if rate is None:
        return None
    return _q(Decimal(base_amount) * rate)
