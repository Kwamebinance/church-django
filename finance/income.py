"""
Income lifecycle — the correctness-critical core. Kept as pure-ish functions so
the rules are testable independent of views.

States (finance_status): pending -> approved / rejected -> voided.
Rules:
  - On create: if the church requires approval -> pending; else -> approved now.
  - Approve/reject: treasurer+, and NOT the submitter (separation of duties).
  - Void: treasurer+; permanent; record kept as history.
Every transition is audit-logged by the caller (views) — the service returns
enough info for a good audit context.
"""
from decimal import Decimal

from django.utils import timezone

from .services import convert_to_base
from .enums import FinanceStatus


class IncomeError(Exception):
    """Raised on an invalid income operation (bad state, self-approval, etc.)."""


def church_requires_approval(church):
    from org.models import ChurchSettings
    s = ChurchSettings.objects.filter(church=church).first()
    # default True when unset (safer: require approval unless explicitly disabled)
    return True if s is None or s.require_income_approval is None else s.require_income_approval


def compute_base_for_lines(church, lines, as_of=None):
    """lines: list of dicts {currency, amount}. Returns (total_base, resolved)
    where resolved is a list of {currency, amount, base_amount, rate} and
    total_base is their sum. Raises IncomeError if any line has no rate."""
    resolved = []
    total = Decimal("0.00")
    for ln in lines:
        amount = Decimal(str(ln["amount"]))
        currency = ln["currency"]
        base_amount, rate = convert_to_base(amount, currency, church, as_of)
        if base_amount is None:
            raise IncomeError(f"No exchange rate available for {currency} → {church.default_currency}.")
        resolved.append({"currency": currency, "amount": amount,
                         "base_amount": base_amount, "rate": rate})
        total += base_amount
    return total, resolved


def create_income(*, profile, church, account, category=None, member=None,
                  received_date, payment_method=None, reference_number=None,
                  notes=None, lines, collected_at=None):
    """Create an income record from one or more currency lines.

    lines: list of {currency, amount} (one entry = single-currency record;
           multiple = multi-currency, stored as child IncomeCurrencyAmount rows).
    collected_at: optional dict {unit_type, department/fellowship/cell id}.
    Returns the created IncomeRecord. Raises IncomeError on a missing rate.
    """
    from .models import IncomeRecord, IncomeCurrencyAmount
    if not lines:
        raise IncomeError("At least one amount is required.")

    as_of = timezone.now()
    total_base, resolved = compute_base_for_lines(church, lines, as_of)

    # ESPEES equivalent, frozen now (universal reference lens). Null if no rate.
    from .services import convert_to_espees
    espees = convert_to_espees(total_base, church, as_of)

    multi = len(lines) > 1
    # for single-currency, the record's amount/currency are that line; for multi,
    # we store the first line on the parent and the full set as children, with
    # the parent amount = total in base currency for display convenience.
    first = resolved[0]
    auto_approved = not church_requires_approval(church)

    rec = IncomeRecord(
        church=church, account=account, category=category, member=member,
        amount=first["amount"], currency=first["currency"],
        base_amount=total_base,
        espees_amount=espees,
        exchange_rate=(first["rate"] if not multi else None),
        received_date=received_date, payment_method=payment_method,
        reference_number=reference_number, notes=notes,
        is_multi_currency=multi,
        status=FinanceStatus.APPROVED if auto_approved else FinanceStatus.PENDING,
        submitted_by=getattr(profile, "pk", None),
        collected_at_church=(collected_at or {}).get("unit_type") in (None, "church"),
        collected_at_unit_type=(collected_at or {}).get("unit_type"),
        collected_at_department_id=(collected_at or {}).get("department_id"),
        collected_at_fellowship_id=(collected_at or {}).get("fellowship_id"),
        collected_at_cell_id=(collected_at or {}).get("cell_id"),
    )
    if auto_approved:
        rec.approved_by = getattr(profile, "pk", None)
        rec.approved_at = as_of
    rec.save()

    if multi:
        for r in resolved:
            IncomeCurrencyAmount.objects.create(
                income_record=rec, currency=r["currency"], amount=r["amount"],
                rate=r["rate"], rate_effective_from=as_of)

    return rec


def approve_income(*, profile, record, reason=None):
    _guard_pending(record)
    _guard_not_submitter(profile, record)
    record.status = FinanceStatus.APPROVED
    record.approved_by = getattr(profile, "pk", None)
    record.approved_at = timezone.now()
    record.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return record


def reject_income(*, profile, record, reason):
    _guard_pending(record)
    _guard_not_submitter(profile, record)
    if not reason:
        raise IncomeError("A rejection reason is required.")
    record.status = FinanceStatus.REJECTED
    record.rejection_reason = reason
    record.save(update_fields=["status", "rejection_reason", "updated_at"])
    return record


def void_income(*, profile, record, reason):
    if record.status == FinanceStatus.VOIDED:
        raise IncomeError("This record is already voided.")
    if not reason:
        raise IncomeError("A void reason is required.")
    record.status = FinanceStatus.VOIDED
    record.voided_by = getattr(profile, "pk", None)
    record.voided_at = timezone.now()
    record.void_reason = reason
    record.save(update_fields=["status", "voided_by", "voided_at", "void_reason", "updated_at"])
    # pledge reversal happens here in slice 4 (when pledges exist)
    return record


def _guard_pending(record):
    if record.status != FinanceStatus.PENDING:
        raise IncomeError(f"Only pending records can be approved or rejected (this is {record.status}).")


def _guard_not_submitter(profile, record):
    if record.submitted_by and getattr(profile, "pk", None) == record.submitted_by:
        # a church with a single treasurer can opt into self-approval
        from org.models import ChurchSettings
        s = ChurchSettings.objects.filter(church=record.church).first()
        if s is not None and s.allow_self_approval:
            return
        raise IncomeError("You cannot approve or reject income you submitted yourself. "
                          "(A treasurer can enable self-approval in finance settings for "
                          "single-treasurer churches.)")
