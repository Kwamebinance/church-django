"""
Core attendance: the named register (attendance_records) and head counts
(count_contributions). Both attach to an AttendanceEvent.

The register's member list is driven by the EVENT's level (church/dept/
fellowship/cell), computed in views -- not stored here. These tables hold only
what was recorded.
"""
import uuid
from datetime import date
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


class VisitorType(models.TextChoices):
    # Real pg_enum: first_time(1), returning(2), special_guest(3).
    FIRST_TIME = "first_time", "First time"
    RETURNING = "returning", "Returning"
    SPECIAL_GUEST = "special_guest", "Special guest"


class FirstTimerStage(models.TextChoices):
    # Real pg_enum: visitor(1), first_timer(2), follow_up(3), integrated(4), member(5).
    VISITOR = "visitor", "Visitor"
    FIRST_TIMER = "first_timer", "First timer"
    FOLLOW_UP = "follow_up", "Follow-up"
    INTEGRATED = "integrated", "Integrated"
    MEMBER = "member", "Member"


class ContactMethod(models.TextChoices):
    # Real pg_enum: call(1), sms(2), whatsapp(3), visit(4), email(5), other(6).
    CALL = "call", "Call"
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"
    VISIT = "visit", "Visit"
    EMAIL = "email", "Email"
    OTHER = "other", "Other"


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"


class AttendanceVisitor(models.Model):
    """A visitor / first-timer captured at an event. Faithful port of
    attendance_visitors. Slice 1 (capture) writes name/phone/stage; the pipeline
    fields (stage_*_at, follow_up_member, assigned_*, converted_to_member) are
    modelled now but used by the follow-up pipeline slice."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.AttendanceEvent", on_delete=models.CASCADE,
                              related_name="visitors", db_column="event_id")
    # --- capture (Slice 1) ---
    name = models.TextField()
    phone = models.TextField(null=True, blank=True)
    email = models.TextField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    invited_by_member = models.ForeignKey("accounts.Member", on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name="invited_visitors",
                                          db_column="invited_by_member_id")
    is_first_time = models.BooleanField(default=True)
    visitor_type = models.CharField(max_length=20, choices=VisitorType.choices,
                                    default=VisitorType.FIRST_TIME)
    responded_to_alter_call = models.BooleanField(default=False)
    alter_call_notes = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    # --- follow-up pipeline (Slice 2) ---
    stage = models.CharField(max_length=20, choices=FirstTimerStage.choices,
                             default=FirstTimerStage.FIRST_TIMER)
    post_service_followup_done = models.BooleanField(default=False)
    follow_up_member = models.ForeignKey("accounts.Member", on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name="following_up_visitors",
                                         db_column="follow_up_member_id")
    assigned_fellowship = models.ForeignKey("org.Fellowship", on_delete=models.SET_NULL,
                                            null=True, blank=True, db_column="assigned_fellowship_id")
    assigned_cell = models.ForeignKey("org.Cell", on_delete=models.SET_NULL,
                                      null=True, blank=True, db_column="assigned_cell_id")
    converted_to_member = models.ForeignKey("accounts.Member", on_delete=models.SET_NULL,
                                            null=True, blank=True, related_name="converted_from_visitor",
                                            db_column="converted_to_member_id")
    stage_first_timer_at = models.DateTimeField(null=True, blank=True)
    stage_follow_up_at = models.DateTimeField(null=True, blank=True)
    stage_integrated_at = models.DateTimeField(null=True, blank=True)
    stage_member_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_visitors"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FirstTimerContact(models.Model):
    """A logged contact attempt with a first-timer (call/sms/visit...). Ported
    now; used by the follow-up pipeline slice."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visitor = models.ForeignKey(AttendanceVisitor, on_delete=models.CASCADE,
                                related_name="contacts", db_column="visitor_id")
    contact_date = models.DateField(default=date.today)
    method = models.CharField(max_length=10, choices=ContactMethod.choices,
                              default=ContactMethod.CALL)
    note = models.TextField(null=True, blank=True)
    contacted_by_member = models.ForeignKey("accounts.Member", on_delete=models.SET_NULL,
                                            null=True, blank=True, db_column="contacted_by_member_id")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "first_timer_contacts"
        ordering = ["-contact_date"]

    def __str__(self):
        return f"{self.get_method_display()} {self.contact_date}"
