"""
Finance configuration management (treasurer+): accounts, categories, currency
rate snapshots, and per-church finance settings. All reach-scoped + audit-logged.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.enums import AccessLevel
from accounts.permissions import can_access, reach_church_ids
from org.models import Church
from .models import FinanceAccount, FinanceCategory, CurrencySnapshot
from org.models import ChurchSettings


def _require_treasurer(request):
    profile = getattr(request, "profile", None)
    if not can_access(profile, AccessLevel.TREASURER):
        raise PermissionDenied("Finance configuration requires treasurer access or above.")
    return profile


def _scoped_churches(profile):
    reach = reach_church_ids(profile)
    qs = Church.objects.filter(status="active")
    return qs if reach is None else qs.filter(id__in=reach)


def _scope_q(profile, qs, church_path="church_id"):
    reach = reach_church_ids(profile)
    if reach is None:
        return qs
    return qs.filter(**{f"{church_path}__in": reach})


# --------------------------------------------------------------------------- #
# Accounts + categories
# --------------------------------------------------------------------------- #
@login_required
def account_list(request):
    profile = _require_treasurer(request)
    accounts = _scope_q(profile, FinanceAccount.objects.select_related("church")
                        ).filter(archived_at__isnull=True).order_by("church__name", "display_order", "name")
    return render(request, "finance/account_list.html", {"accounts": accounts})


@login_required
def account_form(request, account_id=None):
    profile = _require_treasurer(request)
    account = None
    if account_id:
        account = get_object_or_404(_scope_q(profile, FinanceAccount.objects.all()), id=account_id)
    churches = _scoped_churches(profile)
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        short_code = (request.POST.get("short_code") or "").strip()
        church_id = request.POST.get("church_id")
        if not (name and short_code and church_id):
            messages.error(request, "Name, short code, and church are required.")
            return redirect("fin_account_list")
        if account is None:
            account = FinanceAccount(church_id=church_id)
        account.name = name
        account.short_code = short_code
        account.church_id = church_id
        account.is_income = bool(request.POST.get("is_income"))
        try:
            account.display_order = int(request.POST.get("display_order") or 0)
        except ValueError:
            account.display_order = 0
        account.save()
        from audit.services import log_audit
        log_audit(request, table="finance_accounts", row_id=account.id,
                  action="create" if account_id is None else "update",
                  context=f"{'Created' if account_id is None else 'Updated'} finance account: {account.name}",
                  church_id=account.church_id)
        messages.success(request, "Account saved.")
        return redirect("fin_account_list")
    return render(request, "finance/account_form.html", {"a": account, "churches": churches})


@login_required
def account_archive(request, account_id):
    profile = _require_treasurer(request)
    account = get_object_or_404(_scope_q(profile, FinanceAccount.objects.all()), id=account_id)
    if request.method == "POST":
        account.archived_at = timezone.now()
        account.save(update_fields=["archived_at", "updated_at"])
        from audit.services import log_audit
        log_audit(request, table="finance_accounts", row_id=account.id, action="archive",
                  context=f"Archived finance account: {account.name}", church_id=account.church_id)
        messages.success(request, "Account archived.")
    return redirect("fin_account_list")


@login_required
def category_list(request, account_id):
    profile = _require_treasurer(request)
    account = get_object_or_404(_scope_q(profile, FinanceAccount.objects.select_related("church")), id=account_id)
    categories = account.categories.filter(archived_at__isnull=True).order_by("display_order", "name")
    return render(request, "finance/category_list.html", {"account": account, "categories": categories})


@login_required
def category_form(request, account_id, category_id=None):
    profile = _require_treasurer(request)
    account = get_object_or_404(_scope_q(profile, FinanceAccount.objects.all()), id=account_id)
    category = None
    if category_id:
        category = get_object_or_404(account.categories, id=category_id)
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        short_code = (request.POST.get("short_code") or "").strip()
        if not (name and short_code):
            messages.error(request, "Name and short code are required.")
            return redirect("fin_category_list", account_id=account.id)
        if category is None:
            category = FinanceCategory(account=account)
        category.name = name
        category.short_code = short_code
        try:
            category.display_order = int(request.POST.get("display_order") or 0)
        except ValueError:
            category.display_order = 0
        category.save()
        from audit.services import log_audit
        log_audit(request, table="finance_categories", row_id=category.id,
                  action="create" if category_id is None else "update",
                  context=f"{'Created' if category_id is None else 'Updated'} category: {category.name} (account {account.name})",
                  church_id=account.church_id)
        messages.success(request, "Category saved.")
        return redirect("fin_category_list", account_id=account.id)
    return render(request, "finance/category_form.html", {"account": account, "c": category})


# --------------------------------------------------------------------------- #
# Currency snapshots (exchange rates)
# --------------------------------------------------------------------------- #
@login_required
def rate_list(request):
    """Per-church rate board: pick a church, see/enter all the pairs it needs
    (each foreign currency -> base, and ESPEES -> base) in one place. Shows the
    CURRENT rate per pair (latest snapshot), not the full growing history."""
    profile = _require_treasurer(request)
    from .enums import SUPPORTED_CURRENCY_CODES
    churches = list(_scoped_churches(profile))
    # which church's board are we viewing?
    church = None
    cid = request.GET.get("church")
    if cid:
        church = next((c for c in churches if str(c.id) == cid), None)
    if church is None and churches:
        church = churches[0]

    pairs = []
    if church is not None:
        base = church.default_currency
        # the church needs: every other supported currency -> base
        others = [c for c in SUPPORTED_CURRENCY_CODES if c != base]
        for quote in others:
            current = CurrencySnapshot.objects.filter(
                church=church, base_currency=quote, quote_currency=base
            ).order_by("-effective_from").first()
            pairs.append({"quote": quote, "base": base,
                          "rate": current.rate if current else None,
                          "effective_from": current.effective_from if current else None})
    return render(request, "finance/rate_board.html", {
        "churches": churches, "church": church, "pairs": pairs,
    })


@login_required
def rate_save(request):
    """Save the rate board: one or more pairs for a church in a single submit.
    Only creates a new snapshot for pairs whose value changed/was entered."""
    profile = _require_treasurer(request)
    if request.method != "POST":
        return redirect("fin_rate_list")
    from decimal import Decimal, InvalidOperation
    from .enums import SUPPORTED_CURRENCY_CODES
    church = get_object_or_404(_scoped_churches(profile), id=request.POST.get("church_id"))
    base = church.default_currency
    saved = 0
    for quote in [c for c in SUPPORTED_CURRENCY_CODES if c != base]:
        raw = (request.POST.get(f"rate_{quote}") or "").strip()
        if not raw:
            continue
        try:
            rate = Decimal(raw)
        except (InvalidOperation, TypeError):
            continue
        if rate <= 0:
            continue
        # only write a new snapshot if it differs from the current one
        current = CurrencySnapshot.objects.filter(
            church=church, base_currency=quote, quote_currency=base
        ).order_by("-effective_from").first()
        if current and current.rate == rate:
            continue
        snap = CurrencySnapshot.objects.create(
            church=church, base_currency=quote, quote_currency=base, rate=rate,
            effective_from=timezone.now(), source="manual",
            created_by=getattr(profile, "pk", None))
        from audit.services import log_audit
        log_audit(request, table="currency_snapshots", row_id=snap.id, action="create",
                  context=f"Set rate {quote}→{base} = {rate} for {church.name}", church_id=church.id)
        saved += 1
    messages.success(request, f"{saved} rate(s) updated." if saved else "No changes.")
    return redirect(f"{reverse('fin_rate_list')}?church={church.id}")


@login_required
def rate_history(request, church_id):
    """On-demand full history for a church's rates (kept out of the main view)."""
    profile = _require_treasurer(request)
    church = get_object_or_404(_scoped_churches(profile), id=church_id)
    rates = CurrencySnapshot.objects.filter(church=church).order_by("-effective_from")[:300]
    return render(request, "finance/rate_history.html", {"church": church, "rates": rates})


# --------------------------------------------------------------------------- #
# Per-church finance settings
# --------------------------------------------------------------------------- #
@login_required
def settings_view(request, church_id):
    profile = _require_treasurer(request)
    church = get_object_or_404(_scoped_churches(profile), id=church_id)
    settings_obj, _ = ChurchSettings.objects.get_or_create(church=church)
    if request.method == "POST":
        currencies = [c.strip().upper() for c in (request.POST.get("display_currencies") or "").split(",") if c.strip()]
        settings_obj.display_currencies = currencies
        settings_obj.require_income_approval = bool(request.POST.get("require_income_approval"))
        settings_obj.allow_self_approval = bool(request.POST.get("allow_self_approval"))
        settings_obj.updated_by_member_id = getattr(profile, "member_id", None)
        settings_obj.save()
        from audit.services import log_audit
        log_audit(request, table="church_settings", row_id=church.id, action="update",
                  context=f"Updated finance settings for {church.name}", church_id=church.id)
        messages.success(request, "Settings saved.")
        return redirect("fin_settings", church_id=church.id)
    return render(request, "finance/settings.html", {"church": church, "s": settings_obj})


# ============================================================================
# Income recording + lifecycle (treasurer+)
# ============================================================================
from .models import IncomeRecord, IncomeCurrencyAmount
from .enums import FinanceStatus
from . import income as income_svc


@login_required
def income_create(request):
    profile = _require_treasurer(request)
    churches = _scoped_churches(profile)
    accounts = _scope_q(profile, FinanceAccount.objects.filter(is_income=True, archived_at__isnull=True)
                       ).select_related("church")
    if request.method == "POST":
        from datetime import date as _date
        try:
            church = get_object_or_404(churches, id=request.POST.get("church_id"))
            account = get_object_or_404(accounts, id=request.POST.get("account_id"))
            category = None
            if request.POST.get("category_id"):
                category = FinanceCategory.objects.filter(id=request.POST["category_id"], account=account).first()
            member = None
            if request.POST.get("member_id"):
                from accounts.models import Member
                member = Member.objects.filter(id=request.POST["member_id"], church=church).first()
            # currency lines: amount_0/currency_0, amount_1/currency_1, ...
            from .enums import SUPPORTED_CURRENCY_CODES
            lines = []
            i = 0
            while f"amount_{i}" in request.POST:
                amt = request.POST.get(f"amount_{i}")
                cur = (request.POST.get(f"currency_{i}") or "").strip().upper()
                if amt and cur:
                    if cur not in SUPPORTED_CURRENCY_CODES:
                        messages.error(request, f"{cur} is not a supported currency.")
                        return redirect("fin_income_create")
                    lines.append({"amount": amt, "currency": cur})
                i += 1
            if not lines:
                messages.error(request, "Enter at least one amount and currency.")
                return redirect("fin_income_create")
            rec = income_svc.create_income(
                profile=profile, church=church, account=account, category=category,
                member=member,
                received_date=request.POST.get("received_date") or _date.today(),
                payment_method=request.POST.get("payment_method") or None,
                reference_number=request.POST.get("reference_number") or None,
                notes=request.POST.get("notes") or None, lines=lines)
            from audit.services import log_audit
            log_audit(request, table="income_records", row_id=rec.id, action="create",
                      after={"base_amount": str(rec.base_amount), "status": rec.status},
                      context=f"Recorded income {rec.base_amount} {church.default_currency} ({account.name}) — {rec.status}",
                      church_id=church.id)
            messages.success(request, f"Income recorded ({rec.get_status_display() if hasattr(rec,'get_status_display') else rec.status}).")
            return redirect("fin_income_detail", record_id=rec.id)
        except income_svc.IncomeError as e:
            messages.error(request, str(e))
            return redirect("fin_income_create")
    from .enums import SUPPORTED_CURRENCIES
    return render(request, "finance/income_form.html",
                  {"churches": churches, "accounts": accounts, "currencies": SUPPORTED_CURRENCIES})


@login_required
def income_detail(request, record_id):
    profile = _require_treasurer(request)
    rec = get_object_or_404(_scope_q(profile, IncomeRecord.objects.select_related(
        "church", "account", "category", "member")), id=record_id)
    lines = list(rec.currency_amounts.all()) if rec.is_multi_currency else []
    # can the viewer act? (not the submitter, unless church allows self-approval)
    is_submitter = rec.submitted_by and getattr(profile, "pk", None) == rec.submitted_by
    from org.models import ChurchSettings
    _s = ChurchSettings.objects.filter(church=rec.church).first()
    allow_self = bool(_s and _s.allow_self_approval)
    can_act = (not is_submitter) or allow_self
    return render(request, "finance/income_detail.html", {
        "r": rec, "lines": lines, "is_submitter": is_submitter, "can_act": can_act,
        "FinanceStatus": FinanceStatus,
        "hdr_crumbs": [("Record", None)],
    })


def _act_on_income(request, record_id, fn, action_label, *, needs_reason=False):
    profile = _require_treasurer(request)
    rec = get_object_or_404(_scope_q(profile, IncomeRecord.objects.all()), id=record_id)
    if request.method == "POST":
        reason = request.POST.get("reason") or None
        try:
            kwargs = {"profile": profile, "record": rec}
            if needs_reason:
                kwargs["reason"] = reason
            elif reason is not None:
                kwargs["reason"] = reason
            fn(**kwargs)
            from audit.services import log_audit
            log_audit(request, table="income_records", row_id=rec.id, action=action_label,
                      context=f"{action_label.capitalize()} income {rec.base_amount} {rec.church.default_currency} ({rec.account.name})"
                              + (f" — {reason}" if reason else ""),
                      church_id=rec.church_id)
            messages.success(request, f"Income {action_label}.")
        except income_svc.IncomeError as e:
            messages.error(request, str(e))
    return redirect("fin_income_detail", record_id=rec.id)


@login_required
def income_approve(request, record_id):
    return _act_on_income(request, record_id, income_svc.approve_income, "approved")


@login_required
def income_reject(request, record_id):
    return _act_on_income(request, record_id, income_svc.reject_income, "rejected", needs_reason=True)


@login_required
def income_void(request, record_id):
    return _act_on_income(request, record_id, income_svc.void_income, "voided", needs_reason=True)


def pending_income_count(profile):
    """Count of pending income in the viewer's reach (for the nav badge)."""
    if not can_access(profile, AccessLevel.TREASURER):
        return 0
    qs = IncomeRecord.objects.filter(status=FinanceStatus.PENDING)
    reach = reach_church_ids(profile)
    if reach is not None:
        qs = qs.filter(church_id__in=reach)
    return qs.count()


# ============================================================================
# Finance landing page — single sidebar entry, 5 tabs on the page
# ============================================================================
@login_required
def fin_home(request):
    """Finance landing with tabs: Dashboard | Pending approval | Income |
    Expense | Accounts & config. Each tab renders its section inline."""
    profile = _require_treasurer(request)
    tab = request.GET.get("tab", "dashboard")
    valid = {"dashboard", "pending", "income", "expense", "config"}
    if tab not in valid:
        tab = "dashboard"

    # pending count is shown in the tab bar on EVERY tab, so compute it always
    ctx = {"tab": tab, "fin_pending_count": pending_income_count(profile)}

    if tab == "dashboard":
        ctx.update(_dashboard_context(profile))
    elif tab == "pending":
        ctx.update(_pending_context(profile))
    elif tab == "income":
        ctx.update(_income_tab_context(request, profile))
    elif tab == "config":
        ctx.update(_config_context(profile))
    # expense tab is a stub until slice 3

    return render(request, "finance/home.html", ctx)


def _dashboard_context(profile):
    """Basic finance overview: totals by status, pending count, recent activity."""
    from django.db.models import Sum, Count
    qs = _scope_q(profile, IncomeRecord.objects.all())
    approved = qs.filter(status=FinanceStatus.APPROVED)
    # totals are in mixed church base currencies, so group by church
    by_church = (approved.values("church__name", "church__default_currency")
                 .annotate(total=Sum("base_amount"), espees=Sum("espees_amount"), n=Count("id"))
                 .order_by("church__name"))
    pending_n = qs.filter(status=FinanceStatus.PENDING).count()
    recent = (qs.select_related("church", "account")
              .order_by("-created_at")[:8])
    return {
        "dash_by_church": list(by_church),
        "dash_pending_n": pending_n,
        "dash_recent": recent,
        "dash_total_records": qs.count(),
    }


def _pending_context(profile):
    qs = _scope_q(profile, IncomeRecord.objects.select_related(
        "church", "account", "category")).filter(status=FinanceStatus.PENDING
        ).order_by("received_date", "created_at")
    my_pk = getattr(profile, "pk", None)
    return {"pending_rows": [{"r": r, "is_mine": r.submitted_by == my_pk} for r in qs]}


def _income_tab_context(request, profile):
    qs = _scope_q(profile, IncomeRecord.objects.select_related(
        "church", "account", "category", "member")).order_by("-received_date", "-created_at")
    status = request.GET.get("status")
    if status in dict(FinanceStatus.choices):
        qs = qs.filter(status=status)
    from django.core.paginator import Paginator
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    accounts = _scope_q(profile, FinanceAccount.objects.filter(is_income=True, archived_at__isnull=True))
    return {"page": page, "income_status": status or "",
            "income_accounts": accounts, "statuses": FinanceStatus.choices}


def _config_context(profile):
    accounts = _scope_q(profile, FinanceAccount.objects.select_related("church")
                       ).filter(archived_at__isnull=True).order_by("church__name", "display_order", "name")
    return {"config_accounts": accounts, "config_churches": _scoped_churches(profile)}
