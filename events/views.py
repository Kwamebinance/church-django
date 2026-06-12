"""
Events: list (search/filter, reach-scoped), month calendar, detail, create,
edit, cancel.

Access: counter+ for both view and manage (matches the real attendance_events
RLS policy -- counters create/manage events to take attendance against them).
Scope via accounts.permissions.scope_filter so super_admin sees all, others see
their church (finer scope automatically once the scope-walk lands).
"""
import calendar as _cal
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.enums import AccessLevel
from accounts.permissions import can_access, scope_filter
from accounts.models import reach_church_ids
from org.models import Church
from .models import AttendanceEvent, EventStatus
from .forms import EventForm, EventFilterForm


def _require_counter(request):
    profile = getattr(request, "profile", None)
    if not can_access(profile, AccessLevel.COUNTER):
        raise PermissionDenied("You do not have access to events.")
    return profile


def _scoped_churches(profile):
    reach = reach_church_ids(profile)
    qs = Church.objects.filter(status="active")
    return qs if reach is None else qs.filter(id__in=reach)


@login_required
def event_list(request):
    profile = _require_counter(request)
    form = EventFilterForm(request.GET or None)

    qs = (AttendanceEvent.objects.select_related("church", "department", "fellowship", "cell")
          .filter(archived_at__isnull=True))
    qs = scope_filter(qs, profile)

    if form.is_valid():
        if form.cleaned_data.get("q"):
            term = form.cleaned_data["q"]
            qs = qs.filter(Q(title__icontains=term) | Q(location__icontains=term))
        if form.cleaned_data.get("unit_type"):
            qs = qs.filter(unit_type=form.cleaned_data["unit_type"])
        if form.cleaned_data.get("status"):
            qs = qs.filter(status=form.cleaned_data["status"])

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy(); params.pop("page", None)
    return render(request, "events/list.html", {
        "form": form, "page": page, "total": paginator.count,
        "querystring": params.urlencode(),
    })


@login_required
def event_calendar(request):
    profile = _require_counter(request)
    today = date.today()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except (TypeError, ValueError):
        year, month = today.year, today.month
    if not (1 <= month <= 12):
        year, month = today.year, today.month

    first = date(year, month, 1)
    last_day = _cal.monthrange(year, month)[1]
    last = date(year, month, last_day)

    qs = scope_filter(
        AttendanceEvent.objects.filter(archived_at__isnull=True,
                                       event_date__gte=first, event_date__lte=last),
        profile,
    ).select_related("church", "cell", "fellowship", "department").order_by("event_time")

    # bucket events by day
    by_day = {}
    for ev in qs:
        by_day.setdefault(ev.event_date.day, []).append(ev)

    # build the weeks grid (Mon-Sun); calendar.Calendar(firstweekday=0)=Monday
    cal = _cal.Calendar(firstweekday=6)  # Sunday-first, common for church calendars
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        row = []
        for d in week:
            row.append({
                "day": d,
                "in_month": d != 0,
                "is_today": (d != 0 and date(year, month, d) == today),
                "events": by_day.get(d, []) if d != 0 else [],
            })
        weeks.append(row)

    prev_month = (first - timedelta(days=1))
    next_month = (last + timedelta(days=1))
    return render(request, "events/calendar.html", {
        "weeks": weeks, "year": year, "month": month,
        "month_name": _cal.month_name[month],
        "weekday_headers": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "prev": {"year": prev_month.year, "month": prev_month.month},
        "next": {"year": next_month.year, "month": next_month.month},
        "today": today,
    })


@login_required
def event_detail(request, event_id):
    profile = _require_counter(request)
    qs = scope_filter(AttendanceEvent.objects.select_related(
        "church", "department", "fellowship", "cell"), profile)
    event = get_object_or_404(qs, id=event_id)
    return render(request, "events/detail.html", {"e": event})


@login_required
def event_create(request):
    profile = _require_counter(request)
    form = EventForm(request.POST or None, scope_churches=_scoped_churches(profile))
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.recorded_by = request.user
        event.save()
        # Snapshot the expected-attendee list from the event's scope (fixed now).
        from attendance.services import snapshot_expected_attendees
        snapshot_expected_attendees(event, created_by=request.user)
        return redirect("event_detail", event_id=event.id)
    return render(request, "events/form.html", {"form": form, "mode": "create"})


@login_required
def event_edit(request, event_id):
    profile = _require_counter(request)
    qs = scope_filter(AttendanceEvent.objects.all(), profile)
    event = get_object_or_404(qs, id=event_id)
    form = EventForm(request.POST or None, instance=event,
                     scope_churches=_scoped_churches(profile))
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("event_detail", event_id=event.id)
    return render(request, "events/form.html", {"form": form, "mode": "edit", "e": event})


@login_required
def event_cancel(request, event_id):
    profile = _require_counter(request)
    qs = scope_filter(AttendanceEvent.objects.all(), profile)
    event = get_object_or_404(qs, id=event_id)
    if request.method == "POST":
        event.status = EventStatus.CANCELLED
        event.cancelled_at = timezone.now()
        event.cancellation_reason = request.POST.get("reason") or None
        event.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
        return redirect("event_detail", event_id=event.id)
    return render(request, "events/cancel_confirm.html", {"e": event})
