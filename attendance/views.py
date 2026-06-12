"""
Attendance register (expected-list model) + head counts.

The register is built from the event's EXPECTED ATTENDEE list (snapshotted at
event creation), not recomputed from scope. Unmarked = absent (default-absent).
Turnout = (present + late) / expected, shown as count and %.

Access: counter+ within reach to open an event's register.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.enums import AccessLevel
from accounts.models import Member
from accounts.permissions import can_access, scope_filter
from events.models import AttendanceEvent
from .models import AttendanceRecord, CountContribution, AttendancePresence, EventExpectedAttendee
from .services import snapshot_expected_attendees


def _require_counter(request):
    profile = getattr(request, "profile", None)
    if not can_access(profile, AccessLevel.COUNTER):
        raise PermissionDenied("You do not have access to attendance.")
    return profile


def _get_event(profile, event_id):
    return get_object_or_404(
        scope_filter(AttendanceEvent.objects.select_related(
            "church", "cell", "fellowship", "department"), profile),
        id=event_id)


def _is_open(event):
    """A register is editable while attendance is not closed and the event isn't
    cancelled. This is INDEPENDENT of the event's own status (the gathering may
    be 'completed' while attendance recording is still open, and vice versa)."""
    return (not event.attendance_closed) and event.status != "cancelled"


@login_required
def register(request, event_id):
    profile = _require_counter(request)
    event = _get_event(profile, event_id)

    # The roll = the expected list. If empty (e.g. event predates this feature),
    # snapshot now so the register is usable.
    if not event.expected_attendees.exists():
        snapshot_expected_attendees(event, created_by=request.user)

    expected = list(event.expected_attendees.select_related("member", "member__cell")
                    .order_by("member__surname", "member__other_names"))
    records = {r.member_id: r for r in AttendanceRecord.objects.filter(event=event)}

    if request.method == "POST":
        if not _is_open(event):
            messages.error(request, "This register is closed. Reopen it to make changes.")
            return redirect("attendance_register", event_id=event.id)
        action = request.POST.get("action", "save")
        with transaction.atomic():
            if action == "mark_all_present":
                for ea in expected:
                    rec = records.get(ea.member_id)
                    if rec:
                        if rec.presence != AttendancePresence.PRESENT:
                            rec.presence = AttendancePresence.PRESENT
                            rec.recorded_by = request.user
                            rec.save(update_fields=["presence", "recorded_by", "updated_at"])
                    else:
                        AttendanceRecord.objects.create(
                            event=event, member_id=ea.member_id,
                            presence=AttendancePresence.PRESENT, recorded_by=request.user)
                messages.success(request, "Marked everyone present.")
            else:
                # Save explicit marks. Unmarked stays unmarked (= absent by default
                # in the tally); we don't write absent rows en masse.
                valid = dict(AttendancePresence.choices)
                for ea in expected:
                    val = request.POST.get(f"presence_{ea.member_id}")
                    if val not in valid:
                        continue
                    rec = records.get(ea.member_id)
                    if rec:
                        if rec.presence != val:
                            rec.presence = val
                            rec.recorded_by = request.user
                            rec.save(update_fields=["presence", "recorded_by", "updated_at"])
                    else:
                        AttendanceRecord.objects.create(
                            event=event, member_id=ea.member_id, presence=val,
                            recorded_by=request.user)
                messages.success(request, "Attendance saved.")
        return redirect("attendance_register", event_id=event.id)

    rows = []
    for ea in expected:
        rec = records.get(ea.member_id)
        rows.append({
            "member": ea.member,
            "presence": rec.presence if rec else "",
            "is_added": ea.is_added,
        })

    expected_total = len(expected)
    present = sum(1 for r in records.values() if r.presence == "present")
    late = sum(1 for r in records.values() if r.presence == "late")
    excused = sum(1 for r in records.values() if r.presence == "excused")
    explicit_absent = sum(1 for r in records.values() if r.presence == "absent")
    marked_ids = set(records.keys())
    unmarked_absent = sum(1 for ea in expected if ea.member_id not in marked_ids)
    absent_total = explicit_absent + unmarked_absent
    attended = present + late
    turnout_pct = round(attended * 100 / expected_total) if expected_total else 0

    counts = event.count_contributions.select_related("counted_by").order_by("created_at")
    summary = {
        "expected": expected_total, "present": present, "late": late,
        "excused": excused, "absent": absent_total, "attended": attended,
        "turnout_pct": turnout_pct, "head_total": sum(c.count for c in counts),
    }
    return render(request, "attendance/register.html", {
        "event": event, "rows": rows, "presence_choices": AttendancePresence.choices,
        "counts": counts, "summary": summary, "is_open": _is_open(event),
    })


@login_required
def close_register(request, event_id):
    """Close attendance recording (counter+). Read-only until reopened. Does NOT
    change the event's own status -- the gathering and the register are separate."""
    profile = _require_counter(request)
    event = _get_event(profile, event_id)
    if request.method == "POST" and _is_open(event):
        from django.utils import timezone
        event.attendance_closed = True
        event.attendance_closed_at = timezone.now()
        event.attendance_closed_by = request.user
        event.save(update_fields=["attendance_closed", "attendance_closed_at",
                                  "attendance_closed_by", "updated_at"])
        messages.success(request, "Attendance closed. The register is now read-only.")
    return redirect("attendance_register", event_id=event.id)


@login_required
def reopen_register(request, event_id):
    """Reopen attendance (admin+ only)."""
    profile = _require_counter(request)
    event = _get_event(profile, event_id)
    if not can_access(profile, AccessLevel.ADMIN):
        messages.error(request, "Only an admin or above can reopen a closed register.")
        return redirect("attendance_register", event_id=event.id)
    if request.method == "POST" and event.attendance_closed:
        from django.utils import timezone
        event.attendance_closed = False
        event.attendance_reopened_at = timezone.now()
        event.attendance_reopened_by = request.user
        event.save(update_fields=["attendance_closed", "attendance_reopened_at",
                                  "attendance_reopened_by", "updated_at"])
        messages.success(request, "Register reopened for editing.")
    return redirect("attendance_register", event_id=event.id)


@login_required
def add_expected(request, event_id):
    """Add a church member who wasn't auto-expected (is_added=True)."""
    profile = _require_counter(request)
    event = _get_event(profile, event_id)
    if request.method == "POST":
        if not _is_open(event):
            messages.error(request, "This register is closed. Reopen it to make changes.")
            return redirect("attendance_register", event_id=event.id)
        member_id = request.POST.get("member_id")
        if member_id:
            m = Member.objects.filter(id=member_id, church_id=event.church_id,
                                      is_active=True).first()
            if m:
                EventExpectedAttendee.objects.get_or_create(
                    event=event, member=m,
                    defaults={"is_added": True, "created_by": request.user})
                messages.success(request, f"Added {m.surname} {m.other_names} to the register.")
    return redirect("attendance_register", event_id=event.id)


@login_required
def add_expected_search(request, event_id):
    """JSON: church members not already on the expected list, for the add picker."""
    profile = _require_counter(request)
    event = _get_event(profile, event_id)
    q = (request.GET.get("q") or "").strip()
    already = set(event.expected_attendees.values_list("member_id", flat=True))
    qs = Member.objects.filter(church_id=event.church_id, is_active=True,
                               archived_at__isnull=True).exclude(id__in=already)
    if q:
        for term in q.split():
            qs = qs.filter(Q(surname__icontains=term) | Q(other_names__icontains=term)
                           | Q(member_code__icontains=term))
    rows = [{"id": str(m.id), "name": f"{m.surname} {m.other_names}", "code": m.member_code}
            for m in qs.order_by("surname")[:15]]
    return JsonResponse({"results": rows})


@login_required
def add_count(request, event_id):
    profile = _require_counter(request)
    event = _get_event(profile, event_id)
    if request.method == "POST":
        if not _is_open(event):
            messages.error(request, "This register is closed. Reopen it to make changes.")
            return redirect("attendance_register", event_id=event.id)
        try:
            n = int(request.POST.get("count", 0))
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            CountContribution.objects.create(
                event=event, counted_by=request.user,
                label=request.POST.get("label") or None, count=n)
            messages.success(request, f"Added a count of {n}.")
    return redirect("attendance_register", event_id=event.id)


@login_required
def remove_count(request, event_id, count_id):
    profile = _require_counter(request)
    event = _get_event(profile, event_id)
    if request.method == "POST":
        if not _is_open(event):
            messages.error(request, "This register is closed. Reopen it to make changes.")
            return redirect("attendance_register", event_id=event.id)
        CountContribution.objects.filter(id=count_id, event=event).delete()
    return redirect("attendance_register", event_id=event.id)
