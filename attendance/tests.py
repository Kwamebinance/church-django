"""Attendance tests: expected-list register, turnout, default-absent, mark-all,
add-not-expected, head counts. The expected list is snapshotted at event creation;
ORM-created events in tests call snapshot_expected_attendees explicitly."""
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from accounts.models import Profile, Member
from accounts.enums import AccessLevel
from org.models import EcclesiasticalUnit, Church, Department, Fellowship, Cell
from events.models import AttendanceEvent, UnitType
from attendance.models import (AttendanceRecord, CountContribution,
                               EventExpectedAttendee, AttendancePresence)
from attendance.services import snapshot_expected_attendees, event_scope_member_qs

User = get_user_model()


class ExpectedSnapshotTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        d = Department.objects.create(church=self.ch, name="Adults", short_code="AD")
        self.fA = Fellowship.objects.create(church=self.ch, parent_department=d, name="FelA", short_code="FA")
        self.cellA = Cell.objects.create(fellowship=self.fA, name="CellA", short_code="CA")
        self.cellB = Cell.objects.create(fellowship=self.fA, name="CellB", short_code="CB")
        self.mA = Member.objects.create(church=self.ch, member_code="A", surname="Alpha", other_names="A", cell=self.cellA, is_active=True)
        self.mB = Member.objects.create(church=self.ch, member_code="B", surname="Beta", other_names="B", cell=self.cellB, is_active=True)
        self.mNo = Member.objects.create(church=self.ch, member_code="N", surname="Nocell", other_names="N", is_active=True)

    def test_church_event_snapshots_all(self):
        ev = AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH, title="S", event_date=date(2026,6,14))
        n = snapshot_expected_attendees(ev)
        self.assertEqual(n, 3)
        self.assertEqual(set(ev.expected_attendees.values_list("member_id", flat=True)),
                         {self.mA.id, self.mB.id, self.mNo.id})

    def test_cell_event_snapshots_only_cell(self):
        ev = AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CELL, cell=self.cellA, title="C", event_date=date(2026,6,11))
        snapshot_expected_attendees(ev)
        self.assertEqual(set(ev.expected_attendees.values_list("member_id", flat=True)), {self.mA.id})

    def test_snapshot_is_idempotent(self):
        ev = AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH, title="S", event_date=date(2026,6,14))
        snapshot_expected_attendees(ev)
        second = snapshot_expected_attendees(ev)
        self.assertEqual(second, 0)
        self.assertEqual(ev.expected_attendees.count(), 3)


class RegisterTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.m1 = Member.objects.create(church=self.ch, member_code="1", surname="One", other_names="O", is_active=True)
        self.m2 = Member.objects.create(church=self.ch, member_code="2", surname="Two", other_names="T", is_active=True)
        self.m3 = Member.objects.create(church=self.ch, member_code="3", surname="Three", other_names="R", is_active=True)
        self.ev = AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH, title="Service", event_date=date(2026,6,14))
        snapshot_expected_attendees(self.ev)
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_register_lists_expected(self):
        c = Client(); c.force_login(self.su)
        r = c.get(f"/events/{self.ev.id}/register/")
        self.assertEqual(r.status_code, 200)
        for nm in ("One", "Two", "Three"):
            self.assertContains(r, nm)

    def test_save_marks_and_default_absent_turnout(self):
        c = Client(); c.force_login(self.su)
        # mark only m1 present, m2 late; m3 left unmarked -> absent by default
        c.post(f"/events/{self.ev.id}/register/", {
            f"presence_{self.m1.id}": "present",
            f"presence_{self.m2.id}": "late",
        })
        self.assertEqual(AttendanceRecord.objects.get(event=self.ev, member=self.m1).presence, "present")
        self.assertEqual(AttendanceRecord.objects.get(event=self.ev, member=self.m2).presence, "late")
        # m3 has no record (unmarked)
        self.assertFalse(AttendanceRecord.objects.filter(event=self.ev, member=self.m3).exists())
        # turnout = (present 1 + late 1) / expected 3 = 67%
        r = c.get(f"/events/{self.ev.id}/register/")
        self.assertContains(r, "67%")
        self.assertContains(r, "Absent: 1")  # m3 counts absent by default

    def test_mark_all_present(self):
        c = Client(); c.force_login(self.su)
        c.post(f"/events/{self.ev.id}/register/", {"action": "mark_all_present"})
        self.assertEqual(AttendanceRecord.objects.filter(event=self.ev, presence="present").count(), 3)
        r = c.get(f"/events/{self.ev.id}/register/")
        self.assertContains(r, "100%")

    def test_add_not_expected(self):
        # a member not in scope snapshot... here all 3 are expected, so add a 4th
        m4 = Member.objects.create(church=self.ch, member_code="4", surname="Four", other_names="F", is_active=True)
        c = Client(); c.force_login(self.su)
        c.post(f"/events/{self.ev.id}/add-expected/", {"member_id": str(m4.id)})
        ea = EventExpectedAttendee.objects.get(event=self.ev, member=m4)
        self.assertTrue(ea.is_added)
        self.assertEqual(self.ev.expected_attendees.count(), 4)

    def test_counter_access_required(self):
        u = User.objects.create_user(email="m@x.com", password="pw12345678")
        c = Client(); c.force_login(u)
        self.assertEqual(c.get(f"/events/{self.ev.id}/register/").status_code, 403)

    def test_register_renders_with_counted_by_none(self):
        CountContribution.objects.create(event=self.ev, label="Main", count=240)
        c = Client(); c.force_login(self.su)
        r = c.get(f"/events/{self.ev.id}/register/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "240")


class HeadCountTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.ev = AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH, title="S", event_date=date(2026,6,14))
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_counts_sum(self):
        c = Client(); c.force_login(self.su)
        c.post(f"/events/{self.ev.id}/count/", {"label": "Main", "count": "240"})
        c.post(f"/events/{self.ev.id}/count/", {"label": "Overflow", "count": "60"})
        self.assertEqual(sum(x.count for x in CountContribution.objects.filter(event=self.ev)), 300)


class EventCreateSnapshotTests(TestCase):
    """Creating an event via the view should snapshot its expected list."""
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        Member.objects.create(church=self.ch, member_code="1", surname="One", other_names="O", is_active=True)
        Member.objects.create(church=self.ch, member_code="2", surname="Two", other_names="T", is_active=True)
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_create_event_snapshots_expected(self):
        c = Client(); c.force_login(self.su)
        c.post("/events/new/", {
            "title": "Sunday Service", "unit_type": "church",
            "church": str(self.ch.id), "event_date": "2026-06-14", "event_time": "09:00",
        })
        ev = AttendanceEvent.objects.get(title="Sunday Service")
        self.assertEqual(ev.expected_attendees.count(), 2)  # both church members snapshotted


class CloseReopenTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.m1 = Member.objects.create(church=self.ch, member_code="1", surname="One", other_names="O", is_active=True)
        self.ev = AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH, title="S", event_date=date(2026,6,14))
        snapshot_expected_attendees(self.ev)
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")
        # a plain counter
        self.counter = User.objects.create_user(email="c@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.counter)
        p.access_level = AccessLevel.COUNTER; p.church = self.ch; p.save()

    def test_counter_can_close(self):
        c = Client(); c.force_login(self.counter)
        c.post(f"/events/{self.ev.id}/close/")
        self.ev.refresh_from_db()
        self.assertTrue(self.ev.attendance_closed)
        self.assertIsNotNone(self.ev.attendance_closed_at)
        self.assertEqual(self.ev.attendance_closed_by, self.counter)
        # event's OWN status is untouched by closing attendance
        self.assertEqual(self.ev.status, "scheduled")

    def test_closed_register_blocks_edits(self):
        self.ev.attendance_closed = True; self.ev.save()
        c = Client(); c.force_login(self.counter)
        c.post(f"/events/{self.ev.id}/register/", {f"presence_{self.m1.id}": "present"})
        self.assertFalse(AttendanceRecord.objects.filter(event=self.ev, member=self.m1).exists())

    def test_closed_register_is_readonly_in_ui(self):
        self.ev.attendance_closed = True; self.ev.save()
        c = Client(); c.force_login(self.counter)
        r = c.get(f"/events/{self.ev.id}/register/")
        self.assertContains(r, "closed")
        self.assertNotContains(r, "Save attendance")

    def test_counter_cannot_reopen(self):
        self.ev.attendance_closed = True; self.ev.save()
        c = Client(); c.force_login(self.counter)
        c.post(f"/events/{self.ev.id}/reopen/")
        self.ev.refresh_from_db()
        self.assertTrue(self.ev.attendance_closed)  # still closed

    def test_admin_can_reopen(self):
        self.ev.attendance_closed = True; self.ev.save()
        admin = User.objects.create_user(email="a@x.com", password="pw12345678")
        p = Profile.objects.get(user=admin); p.access_level = AccessLevel.ADMIN; p.church = self.ch; p.save()
        c = Client(); c.force_login(admin)
        c.post(f"/events/{self.ev.id}/reopen/")
        self.ev.refresh_from_db()
        self.assertFalse(self.ev.attendance_closed)  # reopened
        self.assertEqual(self.ev.attendance_reopened_by, admin)

    def test_reopened_register_editable_again(self):
        admin = User.objects.create_user(email="a2@x.com", password="pw12345678")
        p = Profile.objects.get(user=admin); p.access_level = AccessLevel.ADMIN; p.church = self.ch; p.save()
        self.ev.attendance_closed = True; self.ev.save()
        c = Client(); c.force_login(admin)
        c.post(f"/events/{self.ev.id}/reopen/")
        c.post(f"/events/{self.ev.id}/register/", {f"presence_{self.m1.id}": "present"})
        self.assertTrue(AttendanceRecord.objects.filter(event=self.ev, member=self.m1, presence="present").exists())
