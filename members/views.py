"""
Members directory: list (search + filter, reach-scoped), detail, create, edit,
archive.

Access: everything here requires unit_leader+ (members are not public). Scope is
applied via accounts.permissions.scope_filter, so super_admin sees all, others
see their church (and finer cell/fellowship scope automatically once the full
scope-walk lands). member_code is auto-generated on create.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Member, generate_member_code
from accounts.enums import AccessLevel
from accounts.permissions import can_access, scope_filter
from org.models import Church
from .forms import MemberForm, MemberFilterForm


def _require_leader(request):
    profile = getattr(request, "profile", None)
    if not can_access(profile, AccessLevel.UNIT_LEADER):
        raise PermissionDenied("You do not have access to the members directory.")
    return profile


def _scoped_churches(profile):
    """Churches the user may file members under (None reach = all active)."""
    from accounts.models import reach_church_ids
    reach = reach_church_ids(profile)
    qs = Church.objects.filter(status="active")
    if reach is None:
        return qs
    return qs.filter(id__in=reach)


@login_required
def member_list(request):
    profile = _require_leader(request)
    form = MemberFilterForm(request.GET or None, scope_churches=_scoped_churches(profile))

    qs = Member.objects.select_related("church", "cell", "cell__fellowship").order_by("surname", "other_names")
    qs = scope_filter(qs, profile)  # Layer 1: reach scoping (church-level)

    # Layer 2: a plain unit_leader (below admin) sees only members of the units
    # they actively lead, not the whole church. admin+ keep full church reach.
    from accounts.permissions import has_at_least, narrow_members_to_led_units
    from accounts.enums import AccessLevel as _AL
    if not has_at_least(profile, _AL.ADMIN):
        qs = narrow_members_to_led_units(qs, profile)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        if q:
            for term in q.split():
                qs = qs.filter(
                    Q(surname__icontains=term) | Q(other_names__icontains=term)
                    | Q(preferred_name__icontains=term)
                    | Q(phone_primary__icontains=term) | Q(phone_whatsapp__icontains=term)
                    | Q(member_code__icontains=term)
                )
        # location filters (zone/group resolve through the church tree)
        if form.cleaned_data.get("zone"):
            z = form.cleaned_data["zone"]
            qs = qs.filter(church__parent_unit__parent_unit=z)  # church -> group -> zone
        if form.cleaned_data.get("group"):
            qs = qs.filter(church__parent_unit=form.cleaned_data["group"])
        if form.cleaned_data.get("church"):
            qs = qs.filter(church=form.cleaned_data["church"])
        if form.cleaned_data.get("fellowship"):
            qs = qs.filter(cell__fellowship=form.cleaned_data["fellowship"])
        if form.cleaned_data.get("cell"):
            qs = qs.filter(cell=form.cleaned_data["cell"])
        if form.cleaned_data.get("department"):
            qs = qs.filter(cell__fellowship__parent_department=form.cleaned_data["department"])
        if form.cleaned_data.get("gender"):
            qs = qs.filter(gender=form.cleaned_data["gender"])
        if form.cleaned_data.get("marital_status"):
            qs = qs.filter(marital_status=form.cleaned_data["marital_status"])
        if form.cleaned_data.get("baptism_status"):
            qs = qs.filter(baptism_status=form.cleaned_data["baptism_status"])
        if form.cleaned_data.get("foundation_school_status"):
            qs = qs.filter(foundation_school_status=form.cleaned_data["foundation_school_status"])
        status = form.cleaned_data.get("status")
        if status == "active":
            qs = qs.filter(is_active=True, archived_at__isnull=True)
        elif status == "inactive":
            qs = qs.filter(Q(is_active=False) | Q(archived_at__isnull=False))
        else:
            qs = qs.filter(archived_at__isnull=True)  # default: hide archived
    else:
        qs = qs.filter(archived_at__isnull=True)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    # active leader assignments for the rows' role labels (one query, not N)
    from access.models import Assignment
    member_ids = [m.id for m in page.object_list]
    role_by_member = {}
    if member_ids:
        for a in (Assignment.objects.filter(member_id__in=member_ids, end_date__isnull=True,
                                             role__is_leader=True)
                  .select_related("role").order_by("member_id")):
            role_by_member.setdefault(a.member_id, a.role.name)

    params = request.GET.copy()
    params.pop("page", None)
    # filter-state flags for the collapsible UI
    loc_keys = ["zone", "group", "church", "fellowship", "cell", "department",
                "gender", "marital_status", "baptism_status", "foundation_school_status", "status"]
    has_location_filters = any(request.GET.get(k) for k in loc_keys)
    has_active_filters = has_location_filters or bool(request.GET.get("q"))
    return render(request, "members/list.html", {
        "form": form, "page": page, "total": paginator.count,
        "querystring": params.urlencode(), "role_by_member": role_by_member,
        "has_location_filters": has_location_filters, "has_active_filters": has_active_filters,
    })


@login_required
def member_detail(request, member_id):
    profile = _require_leader(request)
    qs = scope_filter(Member.objects.select_related("church", "cell", "cell__fellowship", "ministry_group"), profile)
    member = get_object_or_404(qs, id=member_id)

    # active assignments (roles & leadership) — drives header badges + Assignments tab
    from access.models import Assignment
    all_assignments = list(
        Assignment.objects.filter(member=member)
        .select_related("role", "cell", "fellowship", "department")
        .order_by("-role__is_leader", "role__name"))
    assignments = [a for a in all_assignments if a.end_date is None]
    past_assignments = [a for a in all_assignments if a.end_date is not None]

    # which active assignments can THIS user manage (change role / end)?
    from accounts.permissions import can_manage_unit_assignment, can_access as _ca, grantable_roles as _gr
    manageable_ids = set()
    change_role_opts = {}  # assignment_id -> [(role_id, name)]
    for a in assignments:
        ut = "cell" if a.cell_id else "fellowship" if a.fellowship_id else "department" if a.department_id else None
        uid = a.cell_id or a.fellowship_id or a.department_id
        if ut and can_manage_unit_assignment(profile, ut, uid, member.church_id):
            manageable_ids.add(a.id)
            change_role_opts[str(a.id)] = [(str(r.id), r.name) for r in _gr(profile, ut, uid, member.church)]

    # placement cells (admin+ only) for "Change placement"
    can_change_placement = _ca(profile, AccessLevel.ADMIN)
    placement_cells = []
    if can_change_placement:
        from org.models import Cell
        placement_cells = list(Cell.objects.filter(
            fellowship__church_id=member.church_id, archived_at__isnull=True)
            .select_related("fellowship").order_by("fellowship__name", "name"))

    # "Add assignment" options: units in this church the user may manage, each
    # paired with the roles they may grant there. Built for a unit+role picker.
    from accounts.permissions import grantable_roles
    from org.models import Cell as _Cell, Fellowship as _Fel, Department as _Dept
    assign_options = []  # list of {unit_type, unit_id, label, roles:[(id,name)]}
    def _collect(unit_type, qs, label_fn):
        for u in qs:
            if can_manage_unit_assignment(profile, unit_type, u.id, member.church_id):
                roles = [(str(r.id), r.name) for r in grantable_roles(profile, unit_type, u.id, member.church)]
                if roles:
                    assign_options.append({"unit_type": unit_type, "unit_id": str(u.id),
                                           "label": label_fn(u), "roles": roles})
    _collect("cell", _Cell.objects.filter(fellowship__church_id=member.church_id, archived_at__isnull=True).select_related("fellowship"),
             lambda c: f"{c.fellowship.name} · {c.name} (Cell)")
    _collect("fellowship", _Fel.objects.filter(church_id=member.church_id, archived_at__isnull=True),
             lambda f: f"{f.name} (Fellowship)")
    _collect("department", _Dept.objects.filter(church_id=member.church_id, archived_at__isnull=True),
             lambda d: f"{d.name} (Department)")
    import json
    assign_options_json = json.dumps(assign_options)
    change_role_opts_json = json.dumps(change_role_opts)

    # attendance history (most recent first)
    from attendance.models import AttendanceRecord
    records = list(
        AttendanceRecord.objects.filter(member=member)
        .select_related("event").order_by("-event__event_date")[:50])

    # QR (encodes member_code; doubles as typed fallback)
    from .qr import member_qr_svg
    qr_svg = member_qr_svg(member.member_code)

    active_tab = request.GET.get("tab", "profile")
    journey = None
    if active_tab == "journey":
        from .journey import build_journey
        journey = build_journey(member, all_assignments, profile)

    # history tab: this member's audit trail (as the affected row, plus their
    # assignment-row entries), reach already guaranteed by member visibility
    history = None
    if active_tab == "history":
        from audit.models import AuditLog
        assignment_ids = [a.id for a in all_assignments]
        from django.db.models import Q as _Q
        history = list(AuditLog.objects.filter(
            _Q(table_name="members", row_id=member.id)
            | _Q(table_name="assignments", row_id__in=assignment_ids)
        ).order_by("-created_at")[:100])
    tabs = [("profile", "Profile"), ("assignments", "Assignments"), ("family", "Family"),
            ("attendance", "Attendance"), ("finance", "Finance"), ("journey", "Journey"),
            ("history", "History")]
    return render(request, "members/detail.html", {
        "m": member, "assignments": assignments, "past_assignments": past_assignments,
        "manageable_ids": manageable_ids, "records": records,
        "qr_svg": qr_svg, "active_tab": active_tab, "tabs": tabs,
        "can_change_placement": can_change_placement, "placement_cells": placement_cells,
        "assign_options_json": assign_options_json, "has_assign_options": bool(assign_options),
        "change_role_opts_json": change_role_opts_json, "journey": journey,
        "history": history,
    })


@login_required
def member_qr_print(request, member_id):
    """A clean, printable QR card for a member."""
    profile = _require_leader(request)
    qs = scope_filter(Member.objects.select_related("church"), profile)
    member = get_object_or_404(qs, id=member_id)
    from .qr import member_qr_svg
    return render(request, "members/qr_print.html", {
        "m": member, "qr_svg": member_qr_svg(member.member_code)})


@login_required
def member_create(request):
    profile = _require_leader(request)
    if not can_access(profile, AccessLevel.UNIT_LEADER):
        raise PermissionDenied()
    form = MemberForm(request.POST or None, request.FILES or None,
                      scope_churches=_scoped_churches(profile))
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        # member_code: auto-generate using the church template + sequence.
        fellowship_code = (member.cell.fellowship.short_code
                           if member.cell and member.cell.fellowship else "GEN")
        member.member_code = generate_member_code(member.church, fellowship_code)
        if form.cleaned_data.get("photo"):
            member.official_photo_path = _save_photo(form.cleaned_data["photo"])
            member.official_photo_updated_at = timezone.now()
        member.save()
        return redirect("member_detail", member_id=member.id)
    return render(request, "members/form.html", {"form": form, "mode": "create"})


@login_required
def member_edit(request, member_id):
    profile = _require_leader(request)
    qs = scope_filter(Member.objects.all(), profile)
    member = get_object_or_404(qs, id=member_id)
    form = MemberForm(request.POST or None, request.FILES or None,
                      instance=member, scope_churches=_scoped_churches(profile))
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        if form.cleaned_data.get("photo"):
            m.official_photo_path = _save_photo(form.cleaned_data["photo"])
            m.official_photo_updated_at = timezone.now()
        m.save()
        return redirect("member_detail", member_id=m.id)
    return render(request, "members/form.html",
                  {"form": form, "mode": "edit", "m": member})


@login_required
def member_archive(request, member_id):
    profile = _require_leader(request)
    # Archiving is an admin+ action.
    if not can_access(profile, AccessLevel.ADMIN):
        raise PermissionDenied("Archiving a member requires admin access.")
    qs = scope_filter(Member.objects.all(), profile)
    member = get_object_or_404(qs, id=member_id)
    if request.method == "POST":
        member.archived_at = timezone.now()
        member.is_active = False
        member.inactive_reason = request.POST.get("reason") or member.inactive_reason
        member.save(update_fields=["archived_at", "is_active", "inactive_reason"])
        return redirect("member_list")
    return render(request, "members/archive_confirm.html", {"m": member})


def _save_photo(f):
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    import uuid as _u
    ext = (f.name.rsplit(".", 1)[-1] or "jpg").lower()[:5]
    name = f"member_photos/{_u.uuid4().hex}.{ext}"
    return default_storage.save(name, ContentFile(f.read()))


# ============================================================================
# Assignment management (reach + rank + applicability) + photo upload
# These act on the member profile's Assignments tab.
# ============================================================================
def _member_in_reach(profile, member_id):
    qs = scope_filter(Member.objects.all(), profile)
    return get_object_or_404(qs, id=member_id)


@login_required
def assignment_add(request, member_id):
    profile = _require_leader(request)
    member = _member_in_reach(profile, member_id)
    from access.models import Role, Assignment
    from org.models import Cell, Fellowship, Department
    from accounts.permissions import can_manage_unit_assignment, grantable_roles

    if request.method == "POST":
        unit_type = request.POST.get("unit_type")
        unit_id = request.POST.get("unit_id")
        role_id = request.POST.get("role_id")
        if not (unit_type and unit_id and role_id):
            messages.error(request, "Pick a unit and a role.")
            return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")
        # validate the unit belongs to the member's church + permission
        unit_ok, dept_id, fel_id, cell_id = False, None, None, None
        if unit_type == "cell":
            c = Cell.objects.filter(id=unit_id, fellowship__church_id=member.church_id).first()
            if c: unit_ok, cell_id = True, c.id
        elif unit_type == "fellowship":
            f = Fellowship.objects.filter(id=unit_id, church_id=member.church_id).first()
            if f: unit_ok, fel_id = True, f.id
        elif unit_type == "department":
            d = Department.objects.filter(id=unit_id, church_id=member.church_id).first()
            if d: unit_ok, dept_id = True, d.id
        if not unit_ok:
            messages.error(request, "That unit isn't in this member's church.")
            return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")
        if not can_manage_unit_assignment(profile, unit_type, unit_id, member.church_id):
            raise PermissionDenied("You can't manage assignments for that unit.")
        # role must be in the grantable set
        allowed = set(grantable_roles(profile, unit_type, unit_id, member.church).values_list("id", flat=True))
        if str(role_id) not in {str(x) for x in allowed}:
            messages.error(request, "You can't grant that role here.")
            return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")
        new_a = Assignment.objects.create(
            member=member, role_id=role_id, cell_id=cell_id,
            fellowship_id=fel_id, department_id=dept_id)
        from audit.services import log_audit
        log_audit(request, table="assignments", row_id=new_a.id, action="create",
                  after={"role_id": str(role_id), "unit_type": unit_type, "unit_id": str(unit_id)},
                  context=f"Assigned {new_a.role.name} ({unit_type}) to {member.surname} {member.other_names}",
                  church_id=member.church_id)
        messages.success(request, "Assignment added.")
    return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")


@login_required
def assignment_change_role(request, member_id, assignment_id):
    profile = _require_leader(request)
    member = _member_in_reach(profile, member_id)
    from access.models import Assignment
    from accounts.permissions import can_manage_unit_assignment, grantable_roles
    a = get_object_or_404(Assignment.objects.filter(member=member, end_date__isnull=True), id=assignment_id)
    unit_type = ("cell" if a.cell_id else "fellowship" if a.fellowship_id
                 else "department" if a.department_id else None)
    unit_id = a.cell_id or a.fellowship_id or a.department_id
    if request.method == "POST":
        if not can_manage_unit_assignment(profile, unit_type, unit_id, member.church_id):
            raise PermissionDenied("You can't manage assignments for that unit.")
        role_id = request.POST.get("role_id")
        allowed = set(str(x) for x in grantable_roles(profile, unit_type, unit_id, member.church).values_list("id", flat=True))
        if str(role_id) not in allowed:
            messages.error(request, "You can't grant that role here.")
            return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")
        old_role = a.role.name
        a.role_id = role_id
        a.save(update_fields=["role", "updated_at"])
        a.refresh_from_db()
        from audit.services import log_audit
        log_audit(request, table="assignments", row_id=a.id, action="update",
                  before={"role": old_role}, after={"role": a.role.name},
                  context=f"Changed role from {old_role} to {a.role.name} for {member.surname} {member.other_names}",
                  church_id=member.church_id)
        messages.success(request, "Role changed.")
    return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")


@login_required
def assignment_end(request, member_id, assignment_id):
    profile = _require_leader(request)
    member = _member_in_reach(profile, member_id)
    from access.models import Assignment
    from accounts.permissions import can_manage_unit_assignment
    a = get_object_or_404(Assignment.objects.filter(member=member, end_date__isnull=True), id=assignment_id)
    unit_type = ("cell" if a.cell_id else "fellowship" if a.fellowship_id
                 else "department" if a.department_id else None)
    unit_id = a.cell_id or a.fellowship_id or a.department_id
    if request.method == "POST":
        if not can_manage_unit_assignment(profile, unit_type, unit_id, member.church_id):
            raise PermissionDenied("You can't manage assignments for that unit.")
        a.end_date = timezone.now().date()
        a.save(update_fields=["end_date", "updated_at"])
        from audit.services import log_audit
        log_audit(request, table="assignments", row_id=a.id, action="end",
                  after={"end_date": str(a.end_date)},
                  context=f"Ended assignment: {a.role.name} for {member.surname} {member.other_names}",
                  church_id=member.church_id)
        messages.success(request, "Assignment ended (moved to past assignments).")
    return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")


@login_required
def change_placement(request, member_id):
    profile = _require_leader(request)
    if not can_access(profile, AccessLevel.ADMIN):
        raise PermissionDenied("Changing placement requires admin access or above.")
    member = _member_in_reach(profile, member_id)
    from org.models import Cell
    if request.method == "POST":
        cell_id = request.POST.get("cell_id") or None
        if cell_id:
            cell = Cell.objects.filter(id=cell_id, fellowship__church_id=member.church_id).first()
            if cell:
                old_cell = member.cell.name if member.cell else None
                member.cell = cell
                member.save(update_fields=["cell", "updated_at"])
                from audit.services import log_audit
                log_audit(request, table="members", row_id=member.id, action="update",
                          before={"cell": old_cell}, after={"cell": cell.name},
                          context=f"Changed placement to {cell.fellowship.name} · {cell.name}",
                          church_id=member.church_id)
                messages.success(request, "Placement updated.")
            else:
                messages.error(request, "That cell isn't in this member's church.")
    return redirect(reverse("member_detail", args=[member.id]) + "?tab=assignments")


@login_required
def upload_photo(request, member_id):
    profile = _require_leader(request)
    member = _member_in_reach(profile, member_id)
    if request.method == "POST" and request.FILES.get("photo"):
        member.official_photo_path = _save_photo(request.FILES["photo"])
        member.official_photo_updated_at = timezone.now()
        member.save(update_fields=["official_photo_path", "official_photo_updated_at", "updated_at"])
        from audit.services import log_audit
        log_audit(request, table="members", row_id=member.id, action="update",
                  context=f"Updated official photo for {member.surname} {member.other_names}",
                  church_id=member.church_id)
        messages.success(request, "Official photo updated.")
    return redirect("member_detail", member_id=member.id)
