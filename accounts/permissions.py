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
    """Apply reach scoping to a queryset in ONE place.

    super_admin (reach is None) -> unrestricted (returns qs unchanged).
    Everyone else -> filtered to their reach churches.
    Use this everywhere instead of writing church_id__in filters by hand.
    """
    reach = reach_church_ids(profile)
    if reach is None:  # super_admin = all
        return qs
    return qs.filter(**{f"{church_field}__in": reach})


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
