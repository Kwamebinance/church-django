"""
Church services, programmes, and events. Ports the attendance_events table.

An event is a single dated occurrence (a service, meeting, programme) that
attendance can later be recorded against. Scoping is built into the row:
  - church_id (required) + unit_type say WHAT LEVEL the event is at.
  - department_id / fellowship_id / cell_id pin it to a specific unit when the
    unit_type is narrower than church.
So a whole-church Sunday service is unit_type=church with only church_id set;
a cell meeting is unit_type=cell with church_id + cell_id set.

template_id links to the (deferred) recurrence engine; left null for events
created directly. When the event_templates engine is built, generated events
will populate it.
"""
import uuid
from django.conf import settings
from django.db import models


class UnitType(models.TextChoices):
    # Real pg_enum order: department(1), fellowship(2), cell(3), church(4).
    DEPARTMENT = "department", "Department"
    FELLOWSHIP = "fellowship", "Fellowship"
    CELL = "cell", "Cell"
    CHURCH = "church", "Church-wide"


class EventStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class RecurrenceType(models.TextChoices):
    # Real pg_enum order: none(1), weekly(2), monthly(3).
    NONE = "none", "No recurrence"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class WeekPosition(models.TextChoices):
    # Backs recurrence_week_position (month_week_position enum).
    FIRST = "first", "First"
    SECOND = "second", "Second"
    THIRD = "third", "Third"
    FOURTH = "fourth", "Fourth"
    LAST = "last", "Last"


class AttendanceEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # --- scope ---
    church = models.ForeignKey("org.Church", on_delete=models.PROTECT,
                               related_name="events", db_column="church_id")
    unit_type = models.CharField(max_length=20, choices=UnitType.choices,
                                 default=UnitType.CHURCH)
    department = models.ForeignKey("org.Department", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="events",
                                   db_column="department_id")
    fellowship = models.ForeignKey("org.Fellowship", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="events",
                                   db_column="fellowship_id")
    cell = models.ForeignKey("org.Cell", on_delete=models.SET_NULL,
                             null=True, blank=True, related_name="events",
                             db_column="cell_id")

    # --- what / when ---
    title = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    event_date = models.DateField()
    event_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)
    location = models.TextField(null=True, blank=True)

    # --- counts ---
    expected_attendee_count = models.IntegerField(null=True, blank=True)
    head_count = models.IntegerField(null=True, blank=True)

    # --- lifecycle ---
    status = models.CharField(max_length=20, choices=EventStatus.choices,
                              default=EventStatus.SCHEDULED)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(null=True, blank=True)

    # --- recurrence link ---
    template = models.ForeignKey("EventTemplate", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="generated_events", db_column="template_id")

    notes = models.TextField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="recorded_events",
                                    db_column="recorded_by")
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_events"
        ordering = ["-event_date", "-event_time"]

    def __str__(self):
        return f"{self.display_title} on {self.event_date}"

    @property
    def display_title(self):
        if self.title:
            return self.title
        return f"{self.get_unit_type_display()} event"

    @property
    def scope_label(self):
        """Human label for which unit this event belongs to."""
        if self.unit_type == UnitType.CELL and self.cell_id:
            return str(self.cell)
        if self.unit_type == UnitType.FELLOWSHIP and self.fellowship_id:
            return str(self.fellowship)
        if self.unit_type == UnitType.DEPARTMENT and self.department_id:
            return str(self.department)
        return str(self.church)


# ==========================================================================
# Recurrence: EventTemplate + RecurrenceException + the generation engine
# ==========================================================================
from datetime import date as _date, timedelta as _td
import calendar as _calmod


class EventTemplate(models.Model):
    """A recurring pattern that materializes AttendanceEvent rows.

    Scope mirrors AttendanceEvent (church + unit_type + optional unit FK).
    Weekly  -> recurrence_day_of_week (0=Mon .. 6=Sun, Python weekday()).
    Monthly -> either recurrence_day_of_month (e.g. 15) OR
               recurrence_week_position + recurrence_day_of_week (e.g. 3rd Sunday).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    church = models.ForeignKey("org.Church", on_delete=models.PROTECT,
                               related_name="event_templates", db_column="church_id")
    unit_type = models.CharField(max_length=20, choices=UnitType.choices, default=UnitType.CHURCH)
    department = models.ForeignKey("org.Department", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="event_templates", db_column="department_id")
    fellowship = models.ForeignKey("org.Fellowship", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="event_templates", db_column="fellowship_id")
    cell = models.ForeignKey("org.Cell", on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="event_templates", db_column="cell_id")

    title = models.TextField()
    description = models.TextField(null=True, blank=True)

    recurrence_type = models.CharField(max_length=10, choices=RecurrenceType.choices,
                                       default=RecurrenceType.WEEKLY)
    recurrence_day_of_week = models.IntegerField(null=True, blank=True,
                                                 help_text="0=Mon .. 6=Sun")
    recurrence_week_position = models.CharField(max_length=10, choices=WeekPosition.choices,
                                                null=True, blank=True)
    recurrence_day_of_month = models.IntegerField(null=True, blank=True)

    event_time = models.TimeField()
    duration_minutes = models.IntegerField(null=True, blank=True, default=90)
    default_location = models.TextField(null=True, blank=True)

    active_from = models.DateField(default=_date.today)
    active_until = models.DateField(null=True, blank=True)

    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="created_templates",
                                   db_column="created_by")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "event_templates"
        ordering = ["title"]

    def __str__(self):
        return self.title

    @property
    def scope_label(self):
        if self.unit_type == UnitType.CELL and self.cell_id:
            return str(self.cell)
        if self.unit_type == UnitType.FELLOWSHIP and self.fellowship_id:
            return str(self.fellowship)
        if self.unit_type == UnitType.DEPARTMENT and self.department_id:
            return str(self.department)
        return str(self.church)

    # ---- occurrence computation ----
    def occurrence_dates(self, window_start, window_end):
        """All dates this template should occur on within [window_start, window_end],
        respecting active_from/active_until and skipping exception dates."""
        if self.recurrence_type == RecurrenceType.NONE:
            return []

        start = max(window_start, self.active_from)
        end = window_end
        if self.active_until:
            end = min(end, self.active_until)
        if start > end:
            return []

        exceptions = set(
            self.exceptions.filter(exception_date__gte=start, exception_date__lte=end)
            .values_list("exception_date", flat=True)
        )

        dates = []
        if self.recurrence_type == RecurrenceType.WEEKLY:
            if self.recurrence_day_of_week is None:
                return []
            d = start
            while d <= end:
                if d.weekday() == self.recurrence_day_of_week and d not in exceptions:
                    dates.append(d)
                d += _td(days=1)

        elif self.recurrence_type == RecurrenceType.MONTHLY:
            # iterate month by month across the window
            y, m = start.year, start.month
            while _date(y, m, 1) <= end:
                occ = self._monthly_occurrence(y, m)
                if occ and start <= occ <= end and occ not in exceptions:
                    dates.append(occ)
                m += 1
                if m > 12:
                    m = 1; y += 1
        return dates

    def _monthly_occurrence(self, year, month):
        """Resolve this template's single occurrence date in a given month."""
        # by fixed day-of-month
        if self.recurrence_day_of_month:
            last = _calmod.monthrange(year, month)[1]
            day = min(self.recurrence_day_of_month, last)
            return _date(year, month, day)
        # by week-position + weekday (e.g. "third Sunday")
        if self.recurrence_week_position and self.recurrence_day_of_week is not None:
            weekday = self.recurrence_day_of_week
            # all dates in the month matching that weekday
            last = _calmod.monthrange(year, month)[1]
            matches = [ _date(year, month, d) for d in range(1, last + 1)
                        if _date(year, month, d).weekday() == weekday ]
            if not matches:
                return None
            pos = self.recurrence_week_position
            idx = {"first": 0, "second": 1, "third": 2, "fourth": 3}.get(pos)
            if pos == "last":
                return matches[-1]
            if idx is not None and idx < len(matches):
                return matches[idx]
            return None
        return None

    def generate_forward(self, weeks=8, created_by=None):
        """Materialize real AttendanceEvent rows for the next `weeks` weeks.
        Idempotent: never creates a duplicate for a (template, date) already present.
        Returns the number of new events created."""
        window_start = _date.today()
        window_end = window_start + _td(weeks=weeks)
        wanted = self.occurrence_dates(window_start, window_end)
        if not wanted:
            return 0
        existing = set(
            AttendanceEvent.objects.filter(template=self, event_date__in=wanted)
            .values_list("event_date", flat=True)
        )
        created = 0
        for d in wanted:
            if d in existing:
                continue
            AttendanceEvent.objects.create(
                template=self, church=self.church, unit_type=self.unit_type,
                department=self.department, fellowship=self.fellowship, cell=self.cell,
                title=self.title, description=self.description,
                event_date=d, event_time=self.event_time,
                duration_minutes=self.duration_minutes,
                location=self.default_location,
                status=EventStatus.SCHEDULED, recorded_by=created_by,
            )
            created += 1
        return created


class RecurrenceException(models.Model):
    """A date on which a template should NOT generate an occurrence."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(EventTemplate, on_delete=models.CASCADE,
                                 related_name="exceptions", db_column="template_id")
    exception_date = models.DateField()
    reason = models.TextField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, db_column="cancelled_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recurrence_exceptions"
        unique_together = ("template", "exception_date")

    def __str__(self):
        return f"{self.template} skips {self.exception_date}"
