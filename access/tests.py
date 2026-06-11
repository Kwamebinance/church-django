"""
Scope-walk tests -- the security-critical layer. Proves:
  - the corrected access-level ranking matches the live system
  - reach_church_ids resolves church/group/zone role scopes correctly
  - the home-church fallback works for role-less members
  - Layer 2 assignments-based narrowing limits a unit_leader to their led units
"""
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from accounts.models import Profile, Member, reach_church_ids
from accounts.permissions import (
    has_at_least, led_units, narrow_members_to_led_units,
)
from accounts.enums import AccessLevel
from org.models import EcclesiasticalUnit, Church, Department, Fellowship, Cell
from access.models import Role, Assignment, MemberRole

User = get_user_model()


class RankingTests(TestCase):
    """The corrected ladder: zonal > group > church_pastor > admin > ... ; super_admin always passes."""
    def _p(self, level):
        return Profile(access_level=level)

    def test_zonal_pastor_is_highest_tier(self):
        z = self._p(AccessLevel.ZONAL_PASTOR)
        self.assertTrue(has_at_least(z, AccessLevel.GROUP_PASTOR))
        self.assertTrue(has_at_least(z, AccessLevel.CHURCH_PASTOR))
        self.assertTrue(has_at_least(z, AccessLevel.ADMIN))

    def test_church_pastor_below_group_and_zonal(self):
        cp = self._p(AccessLevel.CHURCH_PASTOR)
        self.assertFalse(has_at_least(cp, AccessLevel.GROUP_PASTOR))
        self.assertFalse(has_at_least(cp, AccessLevel.ZONAL_PASTOR))
        self.assertTrue(has_at_least(cp, AccessLevel.ADMIN))  # but above admin

    def test_super_admin_passes_everything(self):
        sa = self._p(AccessLevel.SUPER_ADMIN)
        for lvl in AccessLevel.values:
            self.assertTrue(has_at_least(sa, lvl))

    def test_counter_below_unit_leader(self):
        self.assertFalse(has_at_least(self._p(AccessLevel.COUNTER), AccessLevel.UNIT_LEADER))
        self.assertTrue(has_at_least(self._p(AccessLevel.UNIT_LEADER), AccessLevel.COUNTER))


class ReachWalkTests(TestCase):
    def setUp(self):
        # tree: zone -> group -> churches
        self.zone = EcclesiasticalUnit.objects.create(unit_type="zone", name="Zone 1", short_code="Z1")
        self.group = EcclesiasticalUnit.objects.create(unit_type="group", name="Group A", short_code="GA", parent_unit=self.zone)
        self.group2 = EcclesiasticalUnit.objects.create(unit_type="group", name="Group B", short_code="GB", parent_unit=self.zone)
        self.ch1 = Church.objects.create(name="Church 1", short_code="C1", status="active", parent_unit=self.group)
        self.ch2 = Church.objects.create(name="Church 2", short_code="C2", status="active", parent_unit=self.group)
        self.ch3 = Church.objects.create(name="Church 3", short_code="C3", status="active", parent_unit=self.group2)

    def _member_profile(self, church, level=AccessLevel.UNIT_LEADER):
        m = Member.objects.create(church=church, member_code=f"X-{church.short_code}",
                                  surname="T", other_names="U")
        u = User.objects.create_user(email=f"u-{church.short_code}@x.com", password="pw12345678")
        p = Profile.objects.get(user=u)
        p.member = m; p.access_level = level; p.church = church; p.save()
        return p, m

    def test_church_scope_reaches_that_church(self):
        p, m = self._member_profile(self.ch1)
        MemberRole.objects.create(member=m, level="unit_leader", scope_type="church", scope_id=self.ch1.id)
        self.assertEqual(reach_church_ids(p), {self.ch1.id})

    def test_group_scope_reaches_all_churches_under_group(self):
        p, m = self._member_profile(self.ch1, level=AccessLevel.GROUP_PASTOR)
        MemberRole.objects.create(member=m, level="group_pastor", scope_type="group", scope_id=self.group.id)
        # group A has ch1 + ch2 (not ch3, which is under group B)
        self.assertEqual(reach_church_ids(p), {self.ch1.id, self.ch2.id})

    def test_zone_scope_reaches_all_churches_under_zone(self):
        p, m = self._member_profile(self.ch1, level=AccessLevel.ZONAL_PASTOR)
        MemberRole.objects.create(member=m, level="zonal_pastor", scope_type="zone", scope_id=self.zone.id)
        # whole zone: ch1, ch2 (group A) + ch3 (group B)
        self.assertEqual(reach_church_ids(p), {self.ch1.id, self.ch2.id, self.ch3.id})

    def test_roleless_member_falls_back_to_home_church(self):
        p, m = self._member_profile(self.ch1)
        # no MemberRole rows -> fallback to profile.church_id
        self.assertEqual(reach_church_ids(p), {self.ch1.id})

    def test_super_admin_reach_is_none(self):
        u = User.objects.create_superuser(email="sa@x.com", password="pw12345678")
        p = Profile.objects.get(user=u)
        self.assertIsNone(reach_church_ids(p))


class Layer2NarrowingTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="C", short_code="C", status="active")
        d = Department.objects.create(church=self.ch, name="Adults", short_code="AD")
        self.fA = Fellowship.objects.create(church=self.ch, parent_department=d, name="FelA", short_code="FA")
        self.cellA = Cell.objects.create(fellowship=self.fA, name="CellA", short_code="CA")
        self.cellB = Cell.objects.create(fellowship=self.fA, name="CellB", short_code="CB")
        # members in two different cells
        self.mA = Member.objects.create(church=self.ch, member_code="A1", surname="Alpha", other_names="One", cell=self.cellA)
        self.mB = Member.objects.create(church=self.ch, member_code="B1", surname="Beta", other_names="Two", cell=self.cellB)
        # leader role + assignment to cellA
        self.leader_role = Role.objects.create(church=self.ch, name="Cell Leader", is_leader=True)
        # the unit_leader user, who is mA's... let's make a separate leader member
        self.leaderM = Member.objects.create(church=self.ch, member_code="L1", surname="Lead", other_names="Er", cell=self.cellA)
        Assignment.objects.create(member=self.leaderM, role=self.leader_role, cell=self.cellA)
        self.u = User.objects.create_user(email="lead@x.com", password="pw12345678")
        self.p = Profile.objects.get(user=self.u)
        self.p.member = self.leaderM; self.p.access_level = AccessLevel.UNIT_LEADER; self.p.church = self.ch; self.p.save()

    def test_led_units_reports_cell(self):
        u = led_units(self.p)
        self.assertIn(self.cellA.id, u["cell"])
        self.assertNotIn(self.cellB.id, u["cell"])

    def test_narrowing_limits_to_led_cell(self):
        qs = narrow_members_to_led_units(Member.objects.all(), self.p)
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.mA.id, ids)        # in led cell A
        self.assertIn(self.leaderM.id, ids)   # self
        self.assertNotIn(self.mB.id, ids)     # cell B -> not led -> hidden

    def test_member_list_view_narrows_for_unit_leader(self):
        c = Client(); c.force_login(self.u)
        r = c.get("/members/")
        self.assertContains(r, "Alpha")       # cell A member visible
        self.assertNotContains(r, "Beta")     # cell B member hidden
