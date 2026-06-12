"""
Shared attendance helpers used across apps.

snapshot_expected_attendees(event) builds the expected-attendee list for an
event from its scope (church/department/fellowship/cell). Called at event
creation and when recurrence generates events. Idempotent: won't duplicate.
"""
from accounts.models import Member
from events.models import UnitType


def event_scope_member_qs(event):
    """Active members matching the event's level."""
    qs = Member.objects.filter(church_id=event.church_id, is_active=True,
                               archived_at__isnull=True)
    if event.unit_type == UnitType.CELL and event.cell_id:
        qs = qs.filter(cell_id=event.cell_id)
    elif event.unit_type == UnitType.FELLOWSHIP and event.fellowship_id:
        qs = qs.filter(cell__fellowship_id=event.fellowship_id)
    elif event.unit_type == UnitType.DEPARTMENT and event.department_id:
        qs = qs.filter(cell__fellowship__parent_department_id=event.department_id)
    return qs.order_by("surname", "other_names")


def snapshot_expected_attendees(event, created_by=None):
    """Materialize the scope-derived members into event_expected_attendees
    (is_added=False). Idempotent. Returns the number created."""
    from .models import EventExpectedAttendee
    member_ids = list(event_scope_member_qs(event).values_list("id", flat=True))
    if not member_ids:
        return 0
    existing = set(EventExpectedAttendee.objects.filter(event=event)
                   .values_list("member_id", flat=True))
    to_create = [
        EventExpectedAttendee(event=event, member_id=mid, is_added=False, created_by=created_by)
        for mid in member_ids if mid not in existing
    ]
    if to_create:
        EventExpectedAttendee.objects.bulk_create(to_create)
    return len(to_create)
