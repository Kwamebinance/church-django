"""Audit log tests."""
import uuid
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model

from accounts.models import Member, Profile
from accounts.enums import AccessLevel
from org.models import Church, Department, Fellowship, Cell
from audit.models import AuditLog
from audit.services import log_audit

User = get_user_model()


class AuditModelTests(TestCase):
    def test_entry_is_immutable(self):
        e = AuditLog.objects.create(table_name="members", row_id=uuid.uuid4(), action="create")
        e.action = "update"
        with self.assertRaises(ValueError):
            e.save()

    def test_entry_cannot_be_deleted(self):
        e = AuditLog.objects.create(table_name="members", row_id=uuid.uuid4(), action="create")
        with self.assertRaises(ValueError):
            e.delete()


class AuditHelperTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.user = User.objects.create_user(email="actor@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.user)
        p.access_level = AccessLevel.ADMIN; p.church = self.ch; p.save()

    def test_log_audit_captures_actor(self):
        req = self.rf.post("/x/")
        req.profile = Profile.objects.get(user=self.user)
        rid = uuid.uuid4()
        log_audit(req, table="assignments", row_id=rid, action="end",
                  context="Ended assignment", church_id=self.ch.id)
        e = AuditLog.objects.get(row_id=rid)
        self.assertEqual(e.actor_email, "actor@x.com")
        self.assertEqual(e.actor_id, self.user.id)
        self.assertEqual(e.action, "end")
        self.assertEqual(e.church_id, self.ch.id)

    def test_log_audit_never_raises(self):
        # passing None must not blow up the calling operation
        try:
            log_audit(None, table="members", row_id=uuid.uuid4(), action="update")
        except Exception as e:  # noqa: BLE001
            self.fail(f"log_audit raised: {e}")


class HistoryTabTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.m = Member.objects.create(church=self.ch, member_code="CEG-1",
                                       surname="Obi", other_names="Addo")
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_history_tab_shows_entries(self):
        AuditLog.objects.create(table_name="members", row_id=self.m.id, action="update",
                                context="Changed placement to Faith PCF · Faith Cell 1",
                                actor_email="admin@x.com", church_id=self.ch.id)
        c = Client(); c.force_login(self.su)
        r = c.get(f"/members/{self.m.id}/?tab=history")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Changed placement")
        self.assertContains(r, "admin@x.com")

    def test_history_tab_empty_state(self):
        c = Client(); c.force_login(self.su)
        r = c.get(f"/members/{self.m.id}/?tab=history")
        self.assertContains(r, "No recorded history yet")


class AssignmentAuditIntegrationTests(TestCase):
    """End-to-end: ending an assignment writes an audit entry."""
    def setUp(self):
        from access.models import Role, Assignment
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        d = Department.objects.create(church=self.ch, name="D", short_code="D")
        fel = Fellowship.objects.create(church=self.ch, parent_department=d, name="F", short_code="F")
        self.cell = Cell.objects.create(fellowship=fel, name="Cell", short_code="CE")
        self.m = Member.objects.create(church=self.ch, member_code="CEG-1", surname="A", other_names="B")
        role = Role.objects.create(church=self.ch, name="Member", is_leader=False, rank=10)
        self.a = Assignment.objects.create(member=self.m, role=role, cell=self.cell)
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_ending_assignment_writes_audit(self):
        c = Client(); c.force_login(self.su)
        c.post(f"/members/{self.m.id}/assignment/{self.a.id}/end/")
        e = AuditLog.objects.filter(table_name="assignments", row_id=self.a.id, action="end").first()
        self.assertIsNotNone(e)
        self.assertEqual(e.actor_email, "su@x.com")
