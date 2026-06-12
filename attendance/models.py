"""
Core attendance: the named register (attendance_records) and head counts
(count_contributions). Both attach to an AttendanceEvent.

The register's member list is driven by the EVENT's level (church/dept/
fellowship/cell), computed in views -- not stored here. These tables hold only
what was recorded.
"""
import uuid
from django.conf import settings
from django.db import models


class AttendancePresence(models.TextChoices):
    # Real pg_enum: present(1), absent(2), late(3), excused(4).
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LATE = "late", "Late"
    EXCUSED = "excused", "Excused"


class AttendanceRecord(models.Model):
    """One member's presence at one event. Unique per (event, member)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.AttendanceEvent", on_delete=models.CASCADE,
                              related_name="attendance_records", db_column="event_id")
    member = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                               related_name="attendance_records", db_column="member_id")
    presence = models.CharField(max_length=10, choices=AttendancePresence.choices,
                                default=AttendancePresence.PRESENT)
    arrival_time = models.TimeField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, db_column="recorded_by")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_records"
        unique_together = ("event", "member")

    def __str__(self):
        return f"{self.member} @ {self.event}: {self.presence}"


class CountContribution(models.Model):
    """A labelled head-count submitted for an event. Many per event; summed."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.AttendanceEvent", on_delete=models.CASCADE,
                              related_name="count_contributions", db_column="event_id")
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, db_column="counted_by")
    label = models.TextField(null=True, blank=True)
    count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "count_contributions"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.label or 'Count'}: {self.count}"


class EventExpectedAttendee(models.Model):
    """The snapshot of who is expected at an event. Built at event creation from
    the event's scope (is_added=False). Members added later who weren't auto-
    expected (e.g. a surprise visitor from leadership) get is_added=True.

    The register is built from THIS list, not recomputed from scope -- so the
    expected denominator is fixed when the event is created.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.AttendanceEvent", on_delete=models.CASCADE,
                              related_name="expected_attendees", db_column="event_id")
    member = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                               related_name="expected_for_events", db_column="member_id")
    is_added = models.BooleanField(default=False)  # False = auto from scope; True = added later
    notes = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, db_column="created_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_expected_attendees"
        unique_together = ("event", "member")

    def __str__(self):
        return f"{self.member} expected @ {self.event_id}"
