"""Tests for the first-timers follow-up pipeline."""
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from accounts.models import Profile, Member
from accounts.enums import AccessLevel
from org.models import Church, Department, Fellowship, Cell
from events.models import AttendanceEvent, UnitType
from attendance.models import AttendanceVisitor, FirstTimerContact, FirstTimerStage

User = get_user_model()


class PipelineSetup(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.other = Church.objects.create(name="Other", short_code="OTH", status="active")
        d = Department.objects.create(church=self.ch, name="Adults", short_code="AD")
        self.fel = Fellowship.objects.create(church=self.ch, parent_department=d, name="Grace", short_code="GR")
        self.cell = Cell.objects.create(fellowship=self.fel, name="Cell 1", short_code="C1")
        self.ev = AttendanceEvent.objects.create(church=self.ch, unit_type=UnitType.CHURCH, title="Service", event_date=date(2026,6,14))
        self.ev_other = AttendanceEvent.objects.create(church=self.other, unit_type=UnitType.CHURCH, title="Other Svc", event_date=date(2026,6,14))
        self.v = AttendanceVisitor.objects.create(event=self.ev, name="Kofi Mensah", phone="0244", stage=FirstTimerStage.FIRST_TIMER)
        self.v_other = AttendanceVisitor.objects.create(event=self.ev_other, name="Far Away", stage=FirstTimerStage.FIRST_TIMER)
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")


class QueueTests(PipelineSetup):
    def test_queue_lists_active(self):
        c = Client(); c.force_login(self.su)
        r = c.get("/first-timers/")
        self.assertContains(r, "Kofi Mensah")

    def test_queue_hides_converted_by_default(self):
        m = Member.objects.create(church=self.ch, member_code="X", surname="K", other_names="M")
        self.v.converted_to_member = m; self.v.stage = "member"; self.v.save()
        c = Client(); c.force_login(self.su)
        r = c.get("/first-timers/")
        self.assertNotContains(r, "Kofi Mensah")  # member stage hidden in 'active'
        r2 = c.get("/first-timers/?stage=all")
        self.assertContains(r2, "Kofi Mensah")

    def test_reach_scoping(self):
        # a counter in CEG should not see the other church's visitor
        u = User.objects.create_user(email="c@x.com", password="pw12345678")
        p = Profile.objects.get(user=u); p.access_level = AccessLevel.COUNTER; p.church = self.ch; p.save()
        c = Client(); c.force_login(u)
        r = c.get("/first-timers/?stage=all")
        self.assertContains(r, "Kofi Mensah")
        self.assertNotContains(r, "Far Away")


class TransitionTests(PipelineSetup):
    def test_advance_stage_stamps_timestamp(self):
        c = Client(); c.force_login(self.su)
        c.post(f"/first-timers/{self.v.id}/advance/")
        self.v.refresh_from_db()
        self.assertEqual(self.v.stage, "follow_up")
        self.assertIsNotNone(self.v.stage_follow_up_at)

    def test_advance_does_not_auto_reach_member(self):
        self.v.stage = "integrated"; self.v.save()
        c = Client(); c.force_login(self.su)
        c.post(f"/first-timers/{self.v.id}/advance/")
        self.v.refresh_from_db()
        self.assertEqual(self.v.stage, "integrated")  # not bumped into member

    def test_assign_follow_up_and_cell(self):
        leader = Member.objects.create(church=self.ch, member_code="L", surname="Lead", other_names="Er")
        c = Client(); c.force_login(self.su)
        c.post(f"/first-timers/{self.v.id}/assign/", {
            "follow_up_member_id": str(leader.id), "assigned_cell_id": str(self.cell.id)})
        self.v.refresh_from_db()
        self.assertEqual(self.v.follow_up_member, leader)
        self.assertEqual(self.v.assigned_cell, self.cell)
        self.assertEqual(self.v.assigned_fellowship, self.fel)  # derived from cell

    def test_log_contact_creates_and_advances(self):
        c = Client(); c.force_login(self.su)
        c.post(f"/first-timers/{self.v.id}/contact/", {"method": "call", "note": "Spoke, will visit"})
        self.assertEqual(FirstTimerContact.objects.filter(visitor=self.v).count(), 1)
        self.v.refresh_from_db()
        self.assertEqual(self.v.stage, "follow_up")  # logging nudged first_timer -> follow_up


class ConvertTests(PipelineSetup):
    def test_convert_creates_member_and_links(self):
        c = Client(); c.force_login(self.su)
        # GET prefilled form
        r = c.get(f"/first-timers/{self.v.id}/convert/")
        self.assertEqual(r.status_code, 200)
        # POST to create
        r2 = c.post(f"/first-timers/{self.v.id}/convert/", {
            "church": str(self.ch.id), "surname": "Mensah", "other_names": "Kofi",
            "cell": str(self.cell.id),
            "baptism_status": "not_baptized", "foundation_school_status": "not_enrolled",
        })
        self.v.refresh_from_db()
        self.assertIsNotNone(self.v.converted_to_member_id)
        self.assertEqual(self.v.stage, "member")
        self.assertIsNotNone(self.v.stage_member_at)
        m = self.v.converted_to_member
        self.assertEqual(m.surname, "Mensah")
        self.assertTrue(m.member_code)  # auto-generated

    def test_counter_cannot_convert(self):
        u = User.objects.create_user(email="ct@x.com", password="pw12345678")
        p = Profile.objects.get(user=u); p.access_level = AccessLevel.COUNTER; p.church = self.ch; p.save()
        c = Client(); c.force_login(u)
        r = c.get(f"/first-timers/{self.v.id}/convert/")
        self.assertEqual(r.status_code, 403)  # needs unit_leader+
