"""
Members directory: list (search + filter, reach-scoped), detail, create, edit,
archive.

Access: everything here requires unit_leader+ (members are not public). Scope is
applied via accounts.permissions.scope_filter, so super_admin sees all, others
see their church (and finer cell/fellowship scope automatically once the full
scope-walk lands). member_code is auto-generated on create.
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
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
    form = MemberFilterForm(request.GET or None)

    qs = Member.objects.select_related("church", "cell").order_by("surname", "other_names")
    qs = scope_filter(qs, profile)  # reach scoping in one place

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
        if form.cleaned_data.get("cell"):
            qs = qs.filter(cell=form.cleaned_data["cell"])
        if form.cleaned_data.get("fellowship"):
            qs = qs.filter(cell__fellowship=form.cleaned_data["fellowship"])
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

    # preserve filters across pagination links
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "members/list.html", {
        "form": form, "page": page, "total": paginator.count,
        "querystring": params.urlencode(),
    })


@login_required
def member_detail(request, member_id):
    profile = _require_leader(request)
    qs = scope_filter(Member.objects.select_related("church", "cell"), profile)
    member = get_object_or_404(qs, id=member_id)
    return render(request, "members/detail.html", {"m": member})


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
