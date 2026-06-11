"""
Access-control regression tests. The headline test is
SuperAdminReachTests.test_super_admin_can_load_every_protected_page -- it logs
in as super_admin and asserts every protected page loads (not 403/404). If a
future change re-blocks super_admin anywhere listed, this goes red immediately.

Run with:  python manage.py test accounts
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Profile, has_at_least, reach_church_ids, member_in_reach
from accounts.enums import AccessLevel
from org.models import EcclesiasticalUnit, Church, Department, Fellowship, Cell

User = get_user_model()


class AutoProfileTests(TestCase):
    def test_superuser_gets_super_admin_profile_automatically(self):
        u = User.objects.create_superuser(email="boss@x.com", password="pw12345678")
        prof = Profile.objects.filter(user=u).first()
        self.assertIsNotNone(prof, "createsuperuser must auto-create a Profile")
        self.assertEqual(prof.access_level, AccessLevel.SUPER_ADMIN)

    def test_regular_user_gets_member_profile_automatically(self):
        u = User.objects.create_user(email="joe@x.com", password="pw12345678")
        prof = Profile.objects.filter(user=u).first()
        self.assertIsNotNone(prof)
        self.assertEqual(prof.access_level, AccessLevel.MEMBER)


class AccessRankTests(TestCase):
    def test_ordering_matches_live_ranking(self):
        # Live ladder: zonal > group > church_pastor > admin > ... ; super_admin
        # passes everything. (Corrected from an earlier version that wrongly put
        # church_pastor above super_admin per the enum sort order.)
        zonal = Profile(access_level=AccessLevel.ZONAL_PASTOR)
        cp = Profile(access_level=AccessLevel.CHURCH_PASTOR)
        sa = Profile(access_level=AccessLevel.SUPER_ADMIN)
        member = Profile(access_level=AccessLevel.MEMBER)
        # super_admin passes everything, including the pastor tiers
        self.assertTrue(has_at_least(sa, AccessLevel.ZONAL_PASTOR))
        # zonal is the top non-super tier
        self.assertTrue(has_at_least(zonal, AccessLevel.GROUP_PASTOR))
        self.assertTrue(has_at_least(zonal, AccessLevel.CHURCH_PASTOR))
        # church_pastor is above admin but below group/zonal, and NOT >= super_admin
        self.assertTrue(has_at_least(cp, AccessLevel.ADMIN))
        self.assertFalse(has_at_least(cp, AccessLevel.GROUP_PASTOR))
        self.assertFalse(has_at_least(cp, AccessLevel.SUPER_ADMIN))
        # member is the floor
        self.assertFalse(has_at_least(member, AccessLevel.COUNTER))
        self.assertFalse(has_at_least(None, AccessLevel.MEMBER))


class ReachTests(TestCase):
    def setUp(self):
        self.z = EcclesiasticalUnit.objects.create(unit_type="zone", name="Z1", short_code="Z1")
        self.ch1 = Church.objects.create(name="C1", short_code="C1", status="active", parent_unit=self.z)
        self.ch2 = Church.objects.create(name="C2", short_code="C2", status="active", parent_unit=self.z)

    def test_super_admin_reach_is_all(self):
        u = User.objects.create_superuser(email="sa@x.com", password="pw12345678")
        prof = Profile.objects.get(user=u)
        self.assertIsNone(reach_church_ids(prof), "super_admin reach must be None (=all)")

    def test_admin_reach_is_own_church(self):
        u = User.objects.create_user(email="a@x.com", password="pw12345678")
        prof = Profile.objects.get(user=u)
        prof.access_level = AccessLevel.ADMIN
        prof.church = self.ch1
        prof.save()
        self.assertEqual(reach_church_ids(prof), {self.ch1.id})


class SuperAdminReachTests(TestCase):
    """The permanent safeguard: super_admin must be able to load every page."""

    PROTECTED_PAGE_NAMES = [
        "dashboard",
        "reg_queue",
        "member_list",
        "member_create",
        "event_list",
        "event_calendar",
        "event_create",
        "template_list",
        "template_create",
    ]

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(email="root@x.com", password="pw12345678")
        # Profile auto-created by signal as super_admin.
        self.client.force_login(self.admin)

    def test_super_admin_has_profile(self):
        self.assertTrue(Profile.objects.filter(user=self.admin,
                        access_level=AccessLevel.SUPER_ADMIN).exists())

    def test_super_admin_can_load_every_protected_page(self):
        for name in self.PROTECTED_PAGE_NAMES:
            url = reverse(name)
            resp = self.client.get(url)
            self.assertNotIn(
                resp.status_code, (403, 404),
                msg=f"super_admin was blocked from '{name}' ({url}) "
                    f"with status {resp.status_code} -- the super_admin access "
                    f"bug has regressed. Fix via the central permission layer.",
            )
