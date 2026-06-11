"""Events tests: scope, creation, unit_type validation, calendar."""
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from accounts.models import Profile
from accounts.enums import AccessLevel
from org.models import EcclesiasticalUnit, Church, Department, Fellowship, Cell
from events.models import AttendanceEvent, UnitType, EventStatus

User = get_user_model()


class EventScopeTests(TestCase):
    def setUp(self):
        self.z = EcclesiasticalUnit.objects.create(unit_type="zone", name="Z", short_code="Z")
        self.ch = Church.objects.create(name="CE Gwarimpa", short_code="CEG", status="active", parent_unit=self.z)
        self.other = Church.objects.create(name="CE Other", short_code="CEO", status="active", parent_unit=self.z)
        AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH,
                                       title="Sunday Service", event_date=date(2026, 6, 14))
        AttendanceEvent.objects.create(church=self.other, unit_type=UnitType.CHURCH,
                                       title="Other Church Service", event_date=date(2026, 6, 14))
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")
        self.counter = User.objects.create_user(email="c@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.counter)
        p.access_level = AccessLevel.COUNTER; p.church = self.ch; p.save()

    def test_super_admin_sees_all_events(self):
        c = Client(); c.force_login(self.su)
        r = c.get("/events/")
        self.assertContains(r, "Sunday Service")
        self.assertContains(r, "Other Church Service")

    def test_counter_sees_only_own_church(self):
        c = Client(); c.force_login(self.counter)
        r = c.get("/events/")
        self.assertContains(r, "Sunday Service")
        self.assertNotContains(r, "Other Church Service")

    def test_member_cannot_access_events(self):
        u = User.objects.create_user(email="m@x.com", password="pw12345678")
        # auto-profile is member level
        c = Client(); c.force_login(u)
        r = c.get("/events/")
        self.assertEqual(r.status_code, 403)


class EventCreateTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CE Gwarimpa", short_code="CEG", status="active")
        d = Department.objects.create(church=self.ch, name="Adults", short_code="AD")
        self.f = Fellowship.objects.create(church=self.ch, parent_department=d, name="Men", short_code="MEN")
        self.cell = Cell.objects.create(fellowship=self.f, name="Cell 1", short_code="C1")
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_create_church_event(self):
        c = Client(); c.force_login(self.su)
        r = c.post("/events/new/", {
            "title": "Sunday Service", "unit_type": "church",
            "church": str(self.ch.id), "event_date": "2026-06-14", "event_time": "09:00",
        })
        e = AttendanceEvent.objects.filter(title="Sunday Service").first()
        self.assertIsNotNone(e)
        self.assertEqual(e.unit_type, "church")
        self.assertIsNone(e.cell_id)  # church-wide -> no cell

    def test_cell_event_requires_cell(self):
        c = Client(); c.force_login(self.su)
        r = c.post("/events/new/", {
            "title": "Cell Meeting", "unit_type": "cell",
            "church": str(self.ch.id), "event_date": "2026-06-15",
            # no cell provided -> should fail validation
        })
        self.assertFalse(AttendanceEvent.objects.filter(title="Cell Meeting").exists())
        self.assertContains(r, "Select the cell")

    def test_cell_event_with_cell_succeeds(self):
        c = Client(); c.force_login(self.su)
        c.post("/events/new/", {
            "title": "Cell Meeting", "unit_type": "cell",
            "church": str(self.ch.id), "cell": str(self.cell.id), "event_date": "2026-06-15",
        })
        e = AttendanceEvent.objects.filter(title="Cell Meeting").first()
        self.assertIsNotNone(e)
        self.assertEqual(e.cell_id, self.cell.id)


class EventCalendarTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")
        AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH,
                                       title="Midweek Service", event_date=date(2026, 6, 17))

    def test_calendar_renders_event_in_month(self):
        c = Client(); c.force_login(self.su)
        r = c.get("/events/calendar/?year=2026&month=6")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Midweek Service")
        self.assertContains(r, "June 2026")

    def test_calendar_excludes_other_month(self):
        c = Client(); c.force_login(self.su)
        r = c.get("/events/calendar/?year=2026&month=7")
        self.assertNotContains(r, "Midweek Service")


# ==========================================================================
# Recurrence engine tests -- correctness of date generation + idempotency
# ==========================================================================
from events.models import EventTemplate, RecurrenceException, RecurrenceType, WeekPosition


class RecurrenceEngineTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def _weekly_template(self, dow):
        import datetime
        return EventTemplate.objects.create(
            church=self.ch, unit_type=UnitType.CHURCH, title="Service",
            recurrence_type=RecurrenceType.WEEKLY, recurrence_day_of_week=dow,
            event_time=datetime.time(9, 0), active_from=date(2026, 6, 1),
        )

    def test_weekly_lands_on_correct_weekday(self):
        # Sunday = weekday 6
        t = self._weekly_template(6)
        occ = t.occurrence_dates(date(2026, 6, 1), date(2026, 6, 30))
        # June 2026 Sundays: 7, 14, 21, 28
        self.assertEqual([d.day for d in occ], [7, 14, 21, 28])
        self.assertTrue(all(d.weekday() == 6 for d in occ))

    def test_weekly_respects_active_window(self):
        t = self._weekly_template(6)
        t.active_until = date(2026, 6, 15); t.save()
        occ = t.occurrence_dates(date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual([d.day for d in occ], [7, 14])  # 21, 28 are past active_until

    def test_monthly_third_sunday(self):
        import datetime
        t = EventTemplate.objects.create(
            church=self.ch, unit_type=UnitType.CHURCH, title="Monthly Comm",
            recurrence_type=RecurrenceType.MONTHLY,
            recurrence_week_position=WeekPosition.THIRD, recurrence_day_of_week=6,
            event_time=datetime.time(9, 0), active_from=date(2026, 6, 1))
        occ = t.occurrence_dates(date(2026, 6, 1), date(2026, 6, 30))
        # third Sunday of June 2026 = the 21st
        self.assertEqual([d.day for d in occ], [21])

    def test_monthly_by_day_of_month(self):
        import datetime
        t = EventTemplate.objects.create(
            church=self.ch, unit_type=UnitType.CHURCH, title="15th Meeting",
            recurrence_type=RecurrenceType.MONTHLY, recurrence_day_of_month=15,
            event_time=datetime.time(9, 0), active_from=date(2026, 6, 1))
        occ = t.occurrence_dates(date(2026, 6, 1), date(2026, 8, 31))
        self.assertEqual([(d.month, d.day) for d in occ], [(6, 15), (7, 15), (8, 15)])

    def test_exception_is_skipped(self):
        t = self._weekly_template(6)
        RecurrenceException.objects.create(template=t, exception_date=date(2026, 6, 14))
        occ = t.occurrence_dates(date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual([d.day for d in occ], [7, 21, 28])  # 14 skipped

    def test_generate_forward_is_idempotent(self):
        from datetime import timedelta
        import datetime
        # template whose day is today's weekday, so occurrences fall in the window
        today = date.today()
        t = EventTemplate.objects.create(
            church=self.ch, unit_type=UnitType.CHURCH, title="Idem",
            recurrence_type=RecurrenceType.WEEKLY, recurrence_day_of_week=today.weekday(),
            event_time=datetime.time(9, 0), active_from=today)
        first = t.generate_forward(weeks=4)
        second = t.generate_forward(weeks=4)
        self.assertGreater(first, 0, "should generate some events")
        self.assertEqual(second, 0, "re-running must not duplicate")
        # total events equals the first run's count
        self.assertEqual(AttendanceEvent.objects.filter(template=t).count(), first)

    def test_none_recurrence_generates_nothing(self):
        import datetime
        t = EventTemplate.objects.create(
            church=self.ch, unit_type=UnitType.CHURCH, title="One-off",
            recurrence_type=RecurrenceType.NONE, event_time=datetime.time(9, 0),
            active_from=date(2026, 6, 1))
        self.assertEqual(t.occurrence_dates(date(2026, 6, 1), date(2026, 12, 31)), [])
        self.assertEqual(t.generate_forward(weeks=8), 0)


class TemplateAccessTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.other = Church.objects.create(name="Other", short_code="OTH", status="active")
        import datetime
        EventTemplate.objects.create(church=self.ch, unit_type=UnitType.CHURCH,
            title="My Service", recurrence_type=RecurrenceType.WEEKLY,
            recurrence_day_of_week=6, event_time=datetime.time(9, 0))
        EventTemplate.objects.create(church=self.other, unit_type=UnitType.CHURCH,
            title="Other Service", recurrence_type=RecurrenceType.WEEKLY,
            recurrence_day_of_week=6, event_time=datetime.time(9, 0))
        from accounts.models import Profile
        self.counter = User.objects.create_user(email="c@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.counter)
        p.access_level = AccessLevel.COUNTER; p.church = self.ch; p.save()

    def test_counter_sees_only_own_church_templates(self):
        c = Client(); c.force_login(self.counter)
        r = c.get("/templates/")
        self.assertContains(r, "My Service")
        self.assertNotContains(r, "Other Service")
