"""Expose the pending-income count to all templates for the Finance nav badge."""


def finance_badges(request):
    profile = getattr(request, "profile", None)
    if profile is None:
        return {"pending_income_count": None}
    try:
        from accounts.permissions import can_access
        from accounts.enums import AccessLevel
        if not can_access(profile, AccessLevel.TREASURER):
            return {"pending_income_count": None}  # hides the Finance menu
        from .views import pending_income_count
        return {"pending_income_count": pending_income_count(profile)}
    except Exception:  # noqa: BLE001 - never break rendering over a badge
        return {"pending_income_count": None}
