"""
First-timers follow-up pipeline. Reuses attendance.AttendanceVisitor +
FirstTimerContact (no new tables). Reach-scoped to events in the user's churches.

Stages: first_timer -> follow_up -> integrated -> member (terminal, set on convert).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.enums import AccessLevel
from accounts.models import Member, generate_member_code
from accounts.permissions import can_access, reach_church_ids
from attendance.models import (AttendanceVisitor, FirstTimerContact,
                               FirstTimerStage, ContactMethod)
from org.models import Cell, Fellowship

# stage order for "advance"
_STAGE_ORDER = ["first_timer", "follow_up", "integrated", "member"]
_STAGE_AT_FIELD = {
    "first_timer": "stage_first_timer_at",
    "follow_up": "stage_follow_up_at",
    "integrated": "stage_integrated_at",
    "member": "stage_member_at",
}


def _require_counter(request):
    profile = getattr(request, "profile", None)
    if not can_access(profile, AccessLevel.COUNTER):
        raise PermissionDenied("You do not have access to first-timers.")
    return profile


def _scoped_visitors(profile):
    """Visitors whose event is in the user's reach churches."""
    qs = AttendanceVisitor.objects.select_related(
        "event", "event__church", "follow_up_member", "assigned_cell", "converted_to_member")
    reach = reach_church_ids(profile)
    if reach is None:  # super_admin
        return qs
    return qs.filter(event__church_id__in=reach)


@login_required
def queue(request):
    profile = _require_counter(request)
    qs = _scoped_visitors(profile)
    stage = request.GET.get("stage", "active")
    if stage == "active":
        qs = qs.exclude(stage=FirstTimerStage.MEMBER)  # hide converted by default
    elif stage and stage != "all":
        qs = qs.filter(stage=stage)
    qs = qs.order_by("-created_at")
    return render(request, "firsttimers/queue.html", {
        "visitors": qs, "stage": stage,
        "stages": FirstTimerStage.choices,
    })


@login_required
def detail(request, visitor_id):
    profile = _require_counter(request)
    v = get_object_or_404(_scoped_visitors(profile), id=visitor_id)
    contacts = v.contacts.select_related("contacted_by_member").order_by("-contact_date")
    cells = (Cell.objects.filter(fellowship__church_id=v.event.church_id, archived_at__isnull=True)
             .select_related("fellowship").order_by("fellowship__name", "name"))
    return render(request, "firsttimers/detail.html", {
        "v": v, "contacts": contacts, "cells": cells,
        "contact_methods": ContactMethod.choices,
        "can_convert": can_access(profile, AccessLevel.UNIT_LEADER) and not v.converted_to_member_id,
    })


@login_required
def member_search(request, visitor_id):
    """JSON: members in the visitor's church, for the follow-up-person picker."""
    from django.http import JsonResponse
    from django.db.models import Q
    profile = _require_counter(request)
    v = get_object_or_404(_scoped_visitors(profile), id=visitor_id)
    q = (request.GET.get("q") or "").strip()
    qs = Member.objects.filter(church_id=v.event.church_id, is_active=True,
                               archived_at__isnull=True)
    if q:
        for term in q.split():
            qs = qs.filter(Q(surname__icontains=term) | Q(other_names__icontains=term)
                           | Q(member_code__icontains=term))
    rows = [{"id": str(m.id), "name": f"{m.surname} {m.other_names}", "code": m.member_code}
            for m in qs.order_by("surname")[:15]]
    return JsonResponse({"results": rows})


@login_required
def advance_stage(request, visitor_id):
    profile = _require_counter(request)
    v = get_object_or_404(_scoped_visitors(profile), id=visitor_id)
    if request.method == "POST" and not v.converted_to_member_id:
        try:
            idx = _STAGE_ORDER.index(v.stage)
        except ValueError:
            idx = 0
        # advance to the next stage, but never auto-advance INTO 'member'
        if idx < len(_STAGE_ORDER) - 2:
            new_stage = _STAGE_ORDER[idx + 1]
            v.stage = new_stage
            setattr(v, _STAGE_AT_FIELD[new_stage], timezone.now())
            v.save()
            messages.success(request, f"Moved to {v.get_stage_display()}.")
        else:
            messages.info(request, "Use “Convert to member” to complete the journey.")
    return redirect("ft_detail", visitor_id=v.id)


@login_required
def assign(request, visitor_id):
    profile = _require_counter(request)
    v = get_object_or_404(_scoped_visitors(profile), id=visitor_id)
    if request.method == "POST":
        fm_id = request.POST.get("follow_up_member_id") or None
        cell_id = request.POST.get("assigned_cell_id") or None
        if fm_id:
            m = Member.objects.filter(id=fm_id, church_id=v.event.church_id).first()
            v.follow_up_member = m
        else:
            v.follow_up_member = None
        if cell_id:
            cell = Cell.objects.filter(id=cell_id, fellowship__church_id=v.event.church_id).first()
            v.assigned_cell = cell
            v.assigned_fellowship = cell.fellowship if cell else None
        else:
            v.assigned_cell = None
        v.save()
        messages.success(request, "Assignment updated.")
    return redirect("ft_detail", visitor_id=v.id)


@login_required
def log_contact(request, visitor_id):
    profile = _require_counter(request)
    v = get_object_or_404(_scoped_visitors(profile), id=visitor_id)
    if request.method == "POST":
        method = request.POST.get("method")
        if method in dict(ContactMethod.choices):
            FirstTimerContact.objects.create(
                visitor=v, method=method,
                note=(request.POST.get("note") or "").strip() or None,
                contacted_by_member=profile.member if profile and profile.member_id else None)
            # logging a contact nudges a brand-new first-timer into follow_up
            if v.stage == FirstTimerStage.FIRST_TIMER and not v.converted_to_member_id:
                v.stage = FirstTimerStage.FOLLOW_UP
                v.stage_follow_up_at = timezone.now()
                v.save(update_fields=["stage", "stage_follow_up_at", "updated_at"])
            messages.success(request, "Contact logged.")
    return redirect("ft_detail", visitor_id=v.id)


@login_required
def convert(request, visitor_id):
    """Prefill a member form from the visitor; on save create the Member, link it
    back, and set stage=member. Leader+ (creating a member)."""
    profile = _require_counter(request)
    if not can_access(profile, AccessLevel.UNIT_LEADER):
        raise PermissionDenied("Converting to a member requires unit-leader access or above.")
    v = get_object_or_404(_scoped_visitors(profile), id=visitor_id)
    if v.converted_to_member_id:
        messages.info(request, "This first-timer has already been converted.")
        return redirect("ft_detail", visitor_id=v.id)

    from members.forms import MemberForm
    initial = {}
    # split the visitor name into other_names + surname (best effort)
    parts = (v.name or "").strip().split()
    if len(parts) >= 2:
        initial["surname"] = parts[-1]
        initial["other_names"] = " ".join(parts[:-1])
    elif parts:
        initial["surname"] = parts[0]
    if v.phone:
        initial["phone_primary"] = v.phone
    if v.assigned_cell_id:
        initial["cell"] = v.assigned_cell_id
    initial["church"] = v.event.church_id
    # sensible defaults so a walk-in convert isn't forced to set these
    from accounts.enums import BaptismStatus, FoundationSchoolStatus
    initial.setdefault("baptism_status", BaptismStatus.NOT_BAPTIZED)
    initial.setdefault("foundation_school_status", FoundationSchoolStatus.NOT_ENROLLED)

    from members.views import _scoped_churches, _save_photo
    form = MemberForm(request.POST or None, request.FILES or None,
                      initial=initial, scope_churches=_scoped_churches(profile))
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        fellowship_code = (member.cell.fellowship.short_code
                           if member.cell and member.cell.fellowship else "GEN")
        member.member_code = generate_member_code(member.church, fellowship_code)
        member.save()
        # link back + complete the journey
        v.converted_to_member = member
        v.stage = FirstTimerStage.MEMBER
        v.stage_member_at = timezone.now()
        v.post_service_followup_done = True
        v.save()
        messages.success(request, f"{member.surname} {member.other_names} is now a member.")
        return redirect("member_detail", member_id=member.id)

    return render(request, "firsttimers/convert.html", {"form": form, "v": v})
