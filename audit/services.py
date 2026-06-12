"""
log_audit() — the single entry point for writing audit records. Call it at
meaningful actions (assignment changes, transfers, finance ops, etc.).

The actor is captured from the request's profile (id + email), so the trail
records who acted and survives even if that user is later removed. Failures to
log are swallowed (audit must never break the underlying operation) but the
intent is that every sensitive write is accompanied by a log_audit call.
"""
import logging

logger = logging.getLogger(__name__)


def log_audit(request_or_profile, *, table, row_id, action,
              before=None, after=None, context=None, church_id=None):
    """Write an immutable audit entry.

    request_or_profile: the request (preferred — we read request.profile) or a
        Profile directly. Used to capture actor id + email.
    table, row_id, action: what was affected and how.
    before/after: optional dicts of the changed fields (kept small/relevant).
    context: human description ("Ended assignment: Cell Leader, Faith Cell 1").
    church_id: for reach-scoping the entry.
    """
    from .models import AuditLog
    try:
        profile = _resolve_profile(request_or_profile)
        actor_id = profile.pk if profile is not None else None
        actor_email = None
        if profile is not None and getattr(profile, "user", None) is not None:
            actor_email = profile.user.email
        AuditLog.objects.create(
            actor_id=actor_id, actor_email=actor_email,
            table_name=table, row_id=row_id, action=action,
            before_data=before, after_data=after,
            context=context, church_id=church_id,
        )
    except Exception:  # noqa: BLE001 - auditing must never break the operation
        logger.exception("audit log write failed for %s/%s action=%s", table, row_id, action)


def _resolve_profile(obj):
    if obj is None:
        return None
    # a request with .profile attached by middleware
    prof = getattr(obj, "profile", None)
    if prof is not None:
        return prof
    # already a Profile?
    if obj.__class__.__name__ == "Profile":
        return obj
    return None
