"""Members directory tests: code generation, scope, search/filter."""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from accounts.models import Member, Profile, generate_member_code, MemberIdSequence
from accounts.enums import AccessLevel
from org.models import EcclesiasticalUnit, Church, Department, Fellowship, Cell

User = get_user_model()


class MemberCodeTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CE Gwarimpa", short_code="CEG", status="active")

    def test_code_uses_template_and_increments(self):
        c1 = generate_member_code(self.ch, "MEN")
        c2 = generate_member_code(self.ch, "MEN")
        # default template {CHURCH_CODE}-{YEAR}-{SEQ:00000}
        self.assertTrue(c1.startswith("CEG-"))
        self.assertTrue(c1.endswith("00001"))
        self.assertTrue(c2.endswith("00002"))
        self.assertEqual(MemberIdSequence.objects.get(church=self.ch, fellowship_code="MEN").last_seq, 2)


class MemberDirectoryTests(TestCase):
    def setUp(self):
        self.z = EcclesiasticalUnit.objects.create(unit_type="zone", name="Z", short_code="Z")
        self.ch = Church.objects.create(name="CE Gwarimpa", short_code="CEG", status="active", parent_unit=self.z)
        self.other = Church.objects.create(name="CE Other", short_code="CEO", status="active", parent_unit=self.z)
        d = Department.objects.create(church=self.ch, name="Adults", short_code="AD")
        f = Fellowship.objects.create(church=self.ch, parent_department=d, name="Men", short_code="MEN")
        self.cell = Cell.objects.create(fellowship=f, name="Cell 1", short_code="C1")
        # members in two churches
        Member.objects.create(church=self.ch, member_code="CEG-1", surname="Mensah",
                              other_names="Ama", cell=self.cell, phone_primary="+233200000001")
        Member.objects.create(church=self.other, member_code="CEO-1", surname="Boateng",
                              other_names="Kofi", phone_primary="+233200000002")
        # super_admin
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")
        # church admin (own church only)
        self.admin = User.objects.create_user(email="ad@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.admin)
        p.access_level = AccessLevel.ADMIN; p.church = self.ch; p.save()

    def test_super_admin_sees_all_members(self):
        c = Client(); c.force_login(self.su)
        r = c.get("/members/")
        self.assertContains(r, "Mensah")
        self.assertContains(r, "Boateng")

    def test_church_admin_sees_only_own_church(self):
        c = Client(); c.force_login(self.admin)
        r = c.get("/members/")
        self.assertContains(r, "Mensah")       # own church
        self.assertNotContains(r, "Boateng")   # other church -> scoped out

    def test_search_by_name(self):
        c = Client(); c.force_login(self.su)
        r = c.get("/members/?q=Boateng")
        self.assertContains(r, "Boateng")
        self.assertNotContains(r, "Mensah")

    def test_member_create_autogenerates_code(self):
        c = Client(); c.force_login(self.su)
        r = c.post("/members/new/", {
            "surname": "Test", "other_names": "Person", "gender": "male",
            "church": str(self.ch.id), "cell": str(self.cell.id),
            "country": "Ghana",
            "baptism_status": "not_baptized",
            "foundation_school_status": "not_enrolled",
            "is_active": "on",
        })
        m = Member.objects.filter(surname="Test").first()
        self.assertIsNotNone(m)
        self.assertTrue(m.member_code.startswith("CEG-"), f"got {m.member_code}")

    def test_approval_replaces_pending_code(self):
        # A self-registered member starts with a PENDING- code; approval should
        # swap it for a real one.
        from registration.models import RegistrationRequest, RegistrationWindow
        pend = Member.objects.create(
            church=self.ch, member_code="PENDING-ABCD1234", surname="New",
            other_names="Convert", cell=self.cell, is_active=False)
        u = User.objects.create_user(phone="+233200111222")
        req = RegistrationRequest.objects.create(
            user=u, member=pend, cell=self.cell, church=self.ch)
        c = Client(); c.force_login(self.su)
        c.post(f"/registrations/{req.id}/", {"decision": "approve", "notes": ""})
        pend.refresh_from_db()
        self.assertTrue(pend.is_active)
        self.assertFalse(pend.member_code.startswith("PENDING-"),
                         f"code still provisional: {pend.member_code}")
        self.assertTrue(pend.member_code.startswith("CEG-"))


class MemberProfileQRTests(TestCase):
    def setUp(self):
        from org.models import Church
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.m = Member.objects.create(church=self.ch, member_code="CEG-2026-00411",
                                       surname="Addo", other_names="Obi", is_active=True)
        self.su = get_user_model().objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_qr_svg_generated(self):
        from members.qr import member_qr_svg
        svg = member_qr_svg(self.m.member_code)
        self.assertIn("<svg", svg)
        self.assertGreater(len(svg), 500)

    def test_profile_tab_renders_with_qr(self):
        c = Client(); c.force_login(self.su)
        r = c.get(f"/members/{self.m.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Attendance QR")
        self.assertContains(r, "CEG-2026-00411")
        self.assertContains(r, "<svg")

    def test_tabs_present(self):
        c = Client(); c.force_login(self.su)
        r = c.get(f"/members/{self.m.id}/")
        for label in ["Profile", "Assignments", "Family", "Attendance", "Finance", "Journey", "History"]:
            self.assertContains(r, label)

    def test_stub_tab_renders(self):
        c = Client(); c.force_login(self.su)
        r = c.get(f"/members/{self.m.id}/?tab=finance")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Finance domain")

    def test_qr_print_view(self):
        c = Client(); c.force_login(self.su)
        r = c.get(f"/members/{self.m.id}/qr/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "<svg")
        self.assertContains(r, "CEG-2026-00411")


class AssignmentManagementTests(TestCase):
    def setUp(self):
        from access.models import Role, Assignment, UnitRoleApplicability
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        d = Department.objects.create(church=self.ch, name="Sound", short_code="SND")
        self.fel = Fellowship.objects.create(church=self.ch, parent_department=d, name="Grace", short_code="GR")
        self.cell = Cell.objects.create(fellowship=self.fel, name="Cell 1", short_code="C1")
        self.cell2 = Cell.objects.create(fellowship=self.fel, name="Cell 2", short_code="C2")
        # roles with ranks
        self.cell_leader = Role.objects.create(church=self.ch, name="Cell Leader", is_leader=True, rank=30)
        self.asst = Role.objects.create(church=self.ch, name="Assistant Cell Leader", is_leader=True, rank=20)
        self.member_role = Role.objects.create(church=self.ch, name="Member", is_leader=False, rank=10)
        self.pcf_leader = Role.objects.create(church=self.ch, name="PCF Leader", is_leader=True, rank=50)
        # applicability
        for r, ut in [(self.cell_leader,"cell"),(self.asst,"cell"),(self.member_role,"cell"),
                      (self.pcf_leader,"fellowship"),(self.member_role,"fellowship")]:
            UnitRoleApplicability.objects.create(role=r, unit_type=ut)
        # the target member
        self.m = Member.objects.create(church=self.ch, member_code="CEG-1", surname="Tar", other_names="Get", cell=self.cell)
        # a cell leader user for cell 1
        self.leader_member = Member.objects.create(church=self.ch, member_code="CEG-L", surname="Lead", other_names="Er", cell=self.cell)
        Assignment.objects.create(member=self.leader_member, role=self.cell_leader, cell=self.cell)
        self.leader_user = get_user_model().objects.create_user(email="lead@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.leader_user)
        p.access_level = AccessLevel.UNIT_LEADER; p.church = self.ch; p.member = self.leader_member; p.save()
        self.admin = get_user_model().objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_cell_leader_can_grant_only_below_own_rank(self):
        from accounts.permissions import grantable_roles
        p = Profile.objects.get(user=self.leader_user)
        roles = set(grantable_roles(p, "cell", self.cell.id, self.ch).values_list("name", flat=True))
        # cell leader (rank 30) can grant Assistant (20) + Member (10), NOT Cell Leader (30)
        self.assertIn("Assistant Cell Leader", roles)
        self.assertIn("Member", roles)
        self.assertNotIn("Cell Leader", roles)

    def test_applicability_filters_by_unit_type(self):
        from accounts.permissions import grantable_roles
        # admin sees all applicable roles; PCF Leader applies to fellowship not cell
        p = Profile.objects.get(user=self.admin)
        cell_roles = set(grantable_roles(p, "cell", self.cell.id, self.ch).values_list("name", flat=True))
        self.assertNotIn("PCF Leader", cell_roles)
        fel_roles = set(grantable_roles(p, "fellowship", self.fel.id, self.ch).values_list("name", flat=True))
        self.assertIn("PCF Leader", fel_roles)

    def test_cell_leader_cannot_manage_other_cell(self):
        from accounts.permissions import can_manage_unit_assignment
        p = Profile.objects.get(user=self.leader_user)
        self.assertTrue(can_manage_unit_assignment(p, "cell", self.cell.id, self.ch.id))
        self.assertFalse(can_manage_unit_assignment(p, "cell", self.cell2.id, self.ch.id))

    def test_add_assignment_rejects_too_senior_role(self):
        c = Client(); c.force_login(self.leader_user)
        # try to grant Cell Leader (== own rank) — should be rejected
        c.post(f"/members/{self.m.id}/assignment/add/", {
            "unit_type": "cell", "unit_id": str(self.cell.id), "role_id": str(self.cell_leader.id)})
        from access.models import Assignment
        self.assertFalse(Assignment.objects.filter(member=self.m, role=self.cell_leader).exists())

    def test_add_assignment_allows_below_rank(self):
        c = Client(); c.force_login(self.leader_user)
        c.post(f"/members/{self.m.id}/assignment/add/", {
            "unit_type": "cell", "unit_id": str(self.cell.id), "role_id": str(self.asst.id)})
        from access.models import Assignment
        self.assertTrue(Assignment.objects.filter(member=self.m, role=self.asst, end_date__isnull=True).exists())

    def test_end_assignment_sets_end_date(self):
        from access.models import Assignment
        a = Assignment.objects.create(member=self.m, role=self.member_role, cell=self.cell)
        c = Client(); c.force_login(self.admin)
        c.post(f"/members/{self.m.id}/assignment/{a.id}/end/")
        a.refresh_from_db()
        self.assertIsNotNone(a.end_date)

    def test_change_placement_admin_only(self):
        c = Client(); c.force_login(self.leader_user)  # unit_leader, not admin
        r = c.post(f"/members/{self.m.id}/change-placement/", {"cell_id": str(self.cell2.id)})
        self.assertEqual(r.status_code, 403)
        # admin can
        c2 = Client(); c2.force_login(self.admin)
        c2.post(f"/members/{self.m.id}/change-placement/", {"cell_id": str(self.cell2.id)})
        self.m.refresh_from_db()
        self.assertEqual(self.m.cell, self.cell2)


class JourneyTimelineTests(TestCase):
    def setUp(self):
        from datetime import date
        from access.models import Role, Assignment
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        d = Department.objects.create(church=self.ch, name="Sound", short_code="SND")
        self.fel = Fellowship.objects.create(church=self.ch, parent_department=d, name="Grace", short_code="GR")
        self.cell = Cell.objects.create(fellowship=self.fel, name="Cell 1", short_code="C1")
        self.m = Member.objects.create(
            church=self.ch, member_code="CEG-1", surname="Obi", other_names="Addo",
            cell=self.cell, date_joined=date(2022, 11, 7),
            foundation_school_status="completed", foundation_school_completion_date=date(2023, 3, 1))
        self.leader = Role.objects.create(church=self.ch, name="Cell Leader", is_leader=True, rank=30)
        Assignment.objects.create(member=self.m, role=self.leader, cell=self.cell, start_date=date(2024, 1, 15))
        self.su = get_user_model().objects.create_superuser(email="su@x.com", password="pw12345678")

    def test_journey_has_confirmed_milestones(self):
        from members.journey import build_journey
        from access.models import Assignment
        js = build_journey(self.m, list(Assignment.objects.filter(member=self.m)))
        labels = [m["label"] for m in js]
        self.assertIn("Member Registration", labels)
        self.assertIn("Foundation School", labels)
        self.assertIn("Cell Leader", labels)
        # registration is confirmed (dated)
        reg = next(m for m in js if m["label"] == "Member Registration")
        self.assertEqual(reg["status"], "confirmed")

    def test_journey_includes_pending_partnership(self):
        from members.journey import build_journey
        js = build_journey(self.m, [])
        partnership = next((m for m in js if m["key"] == "partnership"), None)
        self.assertIsNotNone(partnership)
        self.assertEqual(partnership["status"], "pending")

    def test_journey_renders_in_tab(self):
        c = Client(); c.force_login(self.su)
        r = c.get(f"/members/{self.m.id}/?tab=journey")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Member journey")
        self.assertContains(r, "Member Registration")
