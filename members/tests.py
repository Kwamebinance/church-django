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
