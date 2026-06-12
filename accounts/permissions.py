"""
THE central access-control layer. Every access decision in the whole app must
go through this module. Do NOT re-implement access checks inline in views, and
NEVER derive scope from profile.member.church_id directly in a view -- always
call these helpers, which handle the memberless super_admin correctly in ONE
place.

Why this exists: in the previous system, super_admin was repeatedly blocked
because individual checks forgot to special-case it, or derived scope from a
member record that super_admin doesn't have. Centralising it here -- and testing
it -- makes that class of bug structurally impossible to reintroduce silently.

The four primitives live in accounts.models (has_at_least, current_member_id,
reach_church_ids, member_in_reach). This module builds the view-facing guards on
top of them.
"""
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import has_at_least, reach_church_ids
from .enums import AccessLevel


def is_super_admin(profile):
    return profile is not None and profile.access_level == AccessLevel.SUPER_ADMIN


def can_access(profile, min_level):
    """The one function that answers 'is this user allowed at >= min_level?'.

    super_admin always passes (handled in has_at_least via ACCESS_RANK, but we
    keep this wrapper as the named entry point views should call).
    """
    return has_at_least(profile, min_level)


def scope_filter(qs, profile, church_field="church_id"):
    """Apply reach scoping to a queryset in ONE place (Layer 1, church-level).

    super_admin (reach is None) -> unrestricted (returns qs unchanged).
    Everyone else -> filtered to their reach churches.
    Use this everywhere instead of writing church_id__in filters by hand.
    """
    reach = reach_church_ids(profile)
    if reach is None:  # super_admin = all
        return qs
    return qs.filter(**{f"{church_field}__in": reach})


# ---- Layer 2: assignments-based sub-church narrowing -----------------------
def led_units(profile):
    """The units a member ACTIVELY LEADS (via assignments to a leader role).

    Returns a dict of sets: {'cell': {...}, 'fellowship': {...}, 'department': {...}}.
    'Active' = assignment.end_date is null AND the role.is_leader is true.
    Mirrors the can_review_change_request / announcement logic which keys off
    active leader-role assignments to a unit. super_admin / high access levels
    are NOT narrowed (they use Layer 1 reach only) -- callers decide whether to
    apply narrowing based on access level.
    """
    empty = {"cell": set(), "fellowship": set(), "department": set()}
    if profile is None or not profile.member_id:
        return empty
    from access.models import Assignment
    rows = (Assignment.objects
            .filter(member_id=profile.member_id, end_date__isnull=True, role__is_leader=True)
            .values("cell_id", "fellowship_id", "department_id"))
    out = {"cell": set(), "fellowship": set(), "department": set()}
    for r in rows:
        if r["cell_id"]:
            out["cell"].add(r["cell_id"])
        if r["fellowship_id"]:
            out["fellowship"].add(r["fellowship_id"])
        if r["department_id"]:
            out["department"].add(r["department_id"])
    return out


def leads_any_unit(profile):
    u = led_units(profile)
    return bool(u["cell"] or u["fellowship"] or u["department"])


def narrow_members_to_led_units(qs, profile):
    """Narrow a Member queryset to the units this leader actually leads.

    Applied for unit_leader-level users who lead specific cells/fellowships:
    they should see members of THEIR units, not the whole church. Higher access
    (admin+) and super_admin are not narrowed here -- they keep full church/reach
    visibility. If a unit_leader leads nothing, they see only themselves.
    """
    from django.db.models import Q
    u = led_units(profile)
    cond = Q(pk__in=[])
    if u["cell"]:
        cond |= Q(cell_id__in=u["cell"])
    if u["fellowship"]:
        cond |= Q(cell__fellowship_id__in=u["fellowship"])
    # always allow seeing self
    if profile and profile.member_id:
        cond |= Q(id=profile.member_id)
    return qs.filter(cond)


# ---- view guards -----------------------------------------------------------
class AccessRequiredMixin(LoginRequiredMixin):
    """Class-based-view mixin. Set `min_access_level` on the view.

    Guarantees: authenticated, has a profile, and ranks >= min_access_level.
    super_admin passes every level automatically.
    """
    min_access_level = AccessLevel.MEMBER

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # -> login redirect
        profile = getattr(request, "profile", None)
        if not can_access(profile, self.min_access_level):
            raise PermissionDenied("You do not have access to this page.")
        return super().dispatch(request, *args, **kwargs)


def access_required(min_level):
    """Function-view decorator equivalent of AccessRequiredMixin."""
    def deco(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            profile = getattr(request, "profile", None)
            if not request.user.is_authenticated:
                from django.shortcuts import redirect
                from django.conf import settings
                return redirect(f"{settings.LOGIN_URL}")
            if not can_access(profile, min_level):
                raise PermissionDenied("You do not have access to this page.")
            return view(request, *args, **kwargs)
        return wrapped
    return deco


# ---- assignment management (reach + rank + applicability) -------------------
def _my_rank_in_unit(profile, unit_type, unit_id):
    """The highest leader-role rank this user holds in the given unit (or None).
    Used to cap which roles they may grant (must be strictly below this)."""
    if profile is None or not profile.member_id:
        return None
    from access.models import Assignment
    field = {"cell": "cell_id", "fellowship": "fellowship_id", "department": "department_id"}.get(unit_type)
    if not field:
        return None
    rows = (Assignment.objects
            .filter(member_id=profile.member_id, end_date__isnull=True,
                    role__is_leader=True, **{field: unit_id})
            .select_related("role"))
    ranks = [a.role.rank for a in rows]
    return max(ranks) if ranks else None


def can_manage_unit_assignment(profile, unit_type, unit_id, church_id):
    """True if the user may add/change/end assignments for this unit:
      - church_pastor/admin+ over the unit's church, OR
      - an active leader of THIS unit (cell/fellowship/department)."""
    if profile is None:
        return False
    if has_at_least(profile, AccessLevel.CHURCH_PASTOR):
        reach = reach_church_ids(profile)
        return reach is None or church_id in reach
    import uuid as _uuid
    if isinstance(unit_id, str):
        try:
            unit_id = _uuid.UUID(unit_id)
        except (ValueError, TypeError):
            return False
    led = led_units(profile)
    return unit_id in led.get(unit_type, set())


def grantable_roles(profile, unit_type, unit_id, church):
    """Roles this user may grant for the unit: applicable to the unit type, and
    (for non-admins) ranked strictly below the user's own rank in that unit."""
    from access.models import Role, UnitRoleApplicability
    applicable_ids = UnitRoleApplicability.objects.filter(
        unit_type=unit_type, role__church=church).values_list("role_id", flat=True)
    qs = Role.objects.filter(church=church, archived_at__isnull=True, id__in=applicable_ids)
    if has_at_least(profile, AccessLevel.ADMIN):
        return qs.order_by("rank")
    my_rank = _my_rank_in_unit(profile, unit_type, unit_id)
    if my_rank is None:
        return qs.none()
    return qs.filter(rank__lt=my_rank).order_by("rank")
