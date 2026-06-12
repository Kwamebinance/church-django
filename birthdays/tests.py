"""Birthday list tests — focus on the year-agnostic date logic."""
from datetime import date
from unittest import mock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from accounts.models import Member, Profile
from accounts.enums import AccessLevel
from org.models import Church, Department, Fellowship, Cell

User = get_user_model()


class BirthdayLogicTests(TestCase):
    def test_days_until_today(self):
        from birthdays.views import _days_until
        today = date(2026, 6, 12)
        self.assertEqual(_days_until(date(1990, 6, 12), today), 0)

    def test_days_until_future_this_year(self):
        from birthdays.views import _days_until
        today = date(2026, 6, 12)
        self.assertEqual(_days_until(date(1990, 6, 15), today), 3)

    def test_days_until_wraps_to_next_year(self):
        from birthdays.views import _days_until
        today = date(2026, 12, 30)
        # Jan 2 birthday -> 3 days away across the year boundary
        self.assertEqual(_days_until(date(1990, 1, 2), today), 3)

    def test_feb29_handled(self):
        from birthdays.views import _days_until
        today = date(2026, 2, 27)  # non-leap year
        # Feb 29 birthday treated as Feb 28
        self.assertEqual(_days_until(date(2000, 2, 29), today), 1)


class BirthdayListViewTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        d = Department.objects.create(church=self.ch, name="D", short_code="D")
        fel = Fellowship.objects.create(church=self.ch, parent_department=d, name="F", short_code="F")
        self.cell = Cell.objects.create(fellowship=fel, name="Cell", short_code="C")
        self.su = User.objects.create_superuser(email="su@x.com", password="pw12345678")

    def _mk(self, dob):
        import uuid
        return Member.objects.create(church=self.ch, cell=self.cell,
                                     member_code=f"CEG-{uuid.uuid4().hex[:6]}",
                                     surname="B", other_names="Day", date_of_birth=dob, is_active=True)

    def test_today_filter_shows_only_today(self):
        with mock.patch("birthdays.views.date") as md:
            md.today.return_value = date(2026, 6, 12)
            md.side_effect = lambda *a, **k: date(*a, **k)
            self._mk(date(1990, 6, 12))   # today
            self._mk(date(1990, 6, 20))   # not today
            c = Client(); c.force_login(self.su)
            r = c.get("/birthdays/?period=today")
            self.assertContains(r, "<strong>1</strong>")

    def test_month_filter_includes_upcoming(self):
        with mock.patch("birthdays.views.date") as md:
            md.today.return_value = date(2026, 6, 12)
            md.side_effect = lambda *a, **k: date(*a, **k)
            self._mk(date(1990, 6, 12))
            self._mk(date(1990, 6, 30))
            self._mk(date(1990, 9, 1))    # outside month window
            c = Client(); c.force_login(self.su)
            r = c.get("/birthdays/?period=month")
            self.assertContains(r, "<strong>2</strong>")

    def test_generate_card_button_links(self):
        self._mk(date(1990, 6, 12))
        c = Client(); c.force_login(self.su)
        r = c.get("/birthdays/?period=month")
        self.assertContains(r, "Generate card")
        self.assertContains(r, "/generate/")


class CardGeneratorTests(TestCase):
    def setUp(self):
        from datetime import date
        self.ch = Church.objects.create(name="CEG", short_code="CEG", status="active")
        self.m = Member.objects.create(church=self.ch, member_code="CEG-1",
                                       surname="Obi", other_names="Addo", preferred_name="Obi",
                                       date_of_birth=date(1990, 6, 12), is_active=True)
        self.admin = User.objects.create_superuser(email="su@x.com", password="pw12345678")
        # a leader (non-admin) for access checks
        self.leader = User.objects.create_user(email="l@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.leader)
        p.access_level = AccessLevel.UNIT_LEADER; p.church = self.ch; p.save()

    def _template(self):
        from birthdays.models import BirthdayCardTemplate
        return BirthdayCardTemplate.objects.create(church=self.ch, name="Default", is_active=True)

    def test_compose_card_produces_png(self):
        from birthdays.cards import compose_card
        t = self._template()  # no background image -> uses fallback
        png = compose_card(t, self.m, "Happy Birthday, Obi!")
        self.assertTrue(png.startswith(b"\x89PNG"))  # PNG magic bytes
        self.assertGreater(len(png), 1000)

    def test_compose_card_handles_missing_photo(self):
        from birthdays.cards import compose_card
        t = self._template()
        self.m.official_photo_path = None; self.m.display_photo_path = None
        png = compose_card(t, self.m, "Hi")  # should not raise
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_generate_download_returns_png(self):
        self._template()
        c = Client(); c.force_login(self.admin)
        r = c.post(f"/birthdays/{self.m.id}/generate/", {
            "template_id": str(self._template().id), "message": "Happy Birthday!", "download": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertIn("attachment", r["Content-Disposition"])

    def test_template_management_requires_admin(self):
        c = Client(); c.force_login(self.leader)  # unit_leader, not admin
        r = c.get("/birthdays/templates/")
        self.assertEqual(r.status_code, 403)
        c2 = Client(); c2.force_login(self.admin)
        self.assertEqual(c2.get("/birthdays/templates/").status_code, 200)

    def test_generate_button_now_links(self):
        self._template()
        from datetime import date
        from unittest import mock
        with mock.patch("birthdays.views.date") as md:
            md.today.return_value = date(2026, 6, 12)
            md.side_effect = lambda *a, **k: date(*a, **k)
            c = Client(); c.force_login(self.admin)
            r = c.get("/birthdays/?period=today")
            self.assertContains(r, f"/birthdays/{self.m.id}/generate/")
