"""
Currency conversion to a church's base currency.

convert_to_base(amount, currency, church, as_of) returns (base_amount, rate):
  - if currency == church.default_currency -> rate 1, base_amount == amount
  - else find the most recent CurrencySnapshot effective on/before `as_of`,
    matching base=church base, quote=currency, scoped church -> zone -> global.
  - if no rate is found, returns (None, None) so the caller can require a manual
    rate rather than guessing.

Rates are stored directionally as base->quote (e.g. GHS->USD = 0.065 means
1 GHS = 0.065 USD). To convert a `quote`-currency amount INTO base, we divide by
the rate. We also accept an inverse snapshot (quote->base) and multiply.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone


def _quantize(d):
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def find_rate(church, base_currency, quote_currency, as_of=None):
    """Return a Decimal rate to convert ONE unit of quote_currency into
    base_currency, or None. Tries church -> zone -> global, newest effective
    on/before as_of. Handles both base->quote and quote->base snapshots."""
    from .models import CurrencySnapshot
    if base_currency == quote_currency:
        return Decimal("1")
    as_of = as_of or timezone.now()

    zone_unit_id = None
    if church is not None:
        # church's zone (walk up: church -> group -> zone) for zone-scoped rates
        zone_unit_id = _church_zone_id(church)

    # scope tiers: church-specific, then zone, then global (church is null)
    def _lookup(qs):
        # direct base->quote: 1 quote = (1/rate) base  -> to base, multiply by 1/rate
        direct = qs.filter(base_currency=base_currency, quote_currency=quote_currency,
                           effective_from__lte=as_of).order_by("-effective_from").first()
        if direct and direct.rate:
            return Decimal("1") / direct.rate
        # inverse quote->base: 1 quote = rate base -> multiply by rate
        inverse = qs.filter(base_currency=quote_currency, quote_currency=base_currency,
                            effective_from__lte=as_of).order_by("-effective_from").first()
        if inverse and inverse.rate:
            return inverse.rate
        return None

    base_qs = CurrencySnapshot.objects.all()
    # 1) church-specific
    if church is not None:
        r = _lookup(base_qs.filter(church=church))
        if r is not None:
            return r
    # 2) zone-scoped
    if zone_unit_id is not None:
        r = _lookup(base_qs.filter(zone_unit_id=zone_unit_id))
        if r is not None:
            return r
    # 3) global (no church)
    r = _lookup(base_qs.filter(church__isnull=True, zone_unit_id__isnull=True))
    return r


def convert_to_base(amount, currency, church, as_of=None):
    """Convert `amount` of `currency` into the church's base currency.
    Returns (base_amount: Decimal|None, rate: Decimal|None)."""
    amount = Decimal(str(amount))
    base_currency = church.default_currency if church else "GHS"
    if currency == base_currency:
        return _quantize(amount), Decimal("1")
    rate = find_rate(church, base_currency, currency, as_of)
    if rate is None:
        return None, None
    return _quantize(amount * rate), rate


def _church_zone_id(church):
    """Walk church -> parent group -> zone, return the zone unit id (or None)."""
    unit = getattr(church, "parent_unit", None)
    seen = 0
    while unit is not None and seen < 5:
        if getattr(unit, "unit_type", None) == "zone":
            return unit.id
        unit = getattr(unit, "parent_unit", None)
        seen += 1
    return None
