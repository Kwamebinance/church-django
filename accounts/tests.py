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


class NavigationTrailTests(TestCase):
    """The stateless breadcrumb trail (accounts/navigation.py)."""
    def setUp(self):
        from django.test import RequestFactory
        self.rf = RequestFactory()

    def _req(self, path="/x/", trail_token=None):
        url = path
        if trail_token is not None:
            from urllib.parse import urlencode
            url = f"{path}?{urlencode({'trail': trail_token})}"
        return self.rf.get(url)

    def test_encode_decode_roundtrip(self):
        from accounts.navigation import encode_trail, decode_trail
        trail = [{"url": "/finance/", "label": "Finance"}, {"url": "/finance/giving/1/", "label": "Giving"}]
        token = encode_trail(trail)
        req = self._req(trail_token=token)
        out = decode_trail(req)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["label"], "Finance")
        self.assertEqual(out[1]["url"], "/finance/giving/1/")

    def test_append_dedup_truncates_to_ancestor(self):
        from accounts.navigation import append_to_trail
        t = [{"url": "/finance/", "label": "Finance"}, {"url": "/finance/giving/1/", "label": "Giving"}]
        # navigating back up to /finance/ collapses the trail to just that
        t2 = append_to_trail(t, "/finance/", "Finance")
        self.assertEqual(len(t2), 1)
        self.assertEqual(t2[0]["url"], "/finance/")

    def test_append_caps_depth(self):
        from accounts.navigation import append_to_trail, MAX_TRAIL
        t = []
        for i in range(MAX_TRAIL + 3):
            t = append_to_trail(t, f"/p{i}/", f"P{i}")
        self.assertLessEqual(len(t), MAX_TRAIL)

    def test_unsafe_url_rejected(self):
        from accounts.navigation import safe_internal_path
        req = self._req()
        self.assertIsNone(safe_internal_path(req, "https://evil.com/"))
        self.assertIsNone(safe_internal_path(req, "//evil.com/"))
        self.assertEqual(safe_internal_path(req, "/members/"), "/members/")

    def test_decode_ignores_unsafe_entries(self):
        from accounts.navigation import encode_trail, decode_trail
        # a trail containing an external url should be dropped on decode
        token = encode_trail([{"url": "https://evil.com", "label": "Bad"},
                              {"url": "/ok/", "label": "OK"}])
        out = decode_trail(self._req(trail_token=token))
        self.assertEqual([h["url"] for h in out], ["/ok/"])

    def test_back_target_fallback(self):
        from accounts.navigation import back_target, encode_trail
        # no trail -> fallback
        self.assertEqual(back_target(self._req(), "/members/"), "/members/")
        # with trail -> last hop
        token = encode_trail([{"url": "/finance/", "label": "Finance"}])
        self.assertEqual(back_target(self._req(trail_token=token), "/members/"), "/finance/")

    def test_garbage_trail_safe(self):
        from accounts.navigation import decode_trail
        out = decode_trail(self._req(trail_token="!!!not-valid-base64!!!"))
        self.assertEqual(out, [])


class CrumbDedupeTests(TestCase):
    """The crumbs tag must not duplicate the home crumb."""
    def setUp(self):
        from django.test import RequestFactory
        self.rf = RequestFactory()

    def _render_crumbs(self, path, home_url, home_label, current):
        from django.template import Template, Context
        req = self.rf.get(path)
        t = Template("{% load nav %}{% crumbs home_url=h home_label=hl current_label=c %}")
        return t.render(Context({"request": req, "h": home_url, "hl": home_label, "c": current}))

    def test_home_not_duplicated_when_trail_contains_home(self):
        from accounts.navigation import encode_trail
        # trail accidentally contains /members/ (the home)
        token = encode_trail([{"url": "/members/", "label": "Members"}])
        html = self._render_crumbs(f"/members/x/?trail={token}", "/members/", "Members", "Ama")
        # "Members" should appear exactly once
        self.assertEqual(html.count(">Members<"), 1)
        self.assertIn(">Ama<", html)

    def test_cross_module_trail_intact(self):
        from accounts.navigation import encode_trail
        token = encode_trail([{"url": "/finance/", "label": "Finance"},
                              {"url": "/finance/giving/1/", "label": "Giving"}])
        html = self._render_crumbs(f"/members/x/?trail={token}", "/members/", "Members", "Ama")
        self.assertIn(">Members<", html)
        self.assertIn(">Finance<", html)
        self.assertIn(">Giving<", html)
        self.assertEqual(html.count(">Members<"), 1)
