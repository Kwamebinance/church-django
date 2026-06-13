"""Finance foundation tests — currency conversion is the critical logic."""
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Profile
from accounts.enums import AccessLevel
from org.models import Church
from finance.models import FinanceAccount, FinanceCategory, CurrencySnapshot
from org.models import ChurchSettings
from finance.services import convert_to_base, find_rate

User = get_user_model()


class ConversionTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CE Accra", short_code="CEA",
                                        status="active", default_currency="GHS")

    def test_same_currency_is_identity(self):
        base, rate = convert_to_base(Decimal("100"), "GHS", self.ch)
        self.assertEqual(base, Decimal("100.00"))
        self.assertEqual(rate, Decimal("1"))

    def test_direct_rate_conversion(self):
        # 1 GHS = 0.083 USD  => 10 USD should be 10 / 0.083 = ~120.48 GHS
        CurrencySnapshot.objects.create(church=self.ch, base_currency="GHS",
                                        quote_currency="USD", rate=Decimal("0.083"),
                                        effective_from=timezone.now() - timedelta(days=1))
        base, rate = convert_to_base(Decimal("10"), "USD", self.ch)
        self.assertIsNotNone(base)
        self.assertAlmostEqual(float(base), 120.48, places=1)

    def test_inverse_rate_conversion(self):
        # stored as USD->GHS: 1 USD = 12 GHS  => 10 USD = 120 GHS
        CurrencySnapshot.objects.create(church=self.ch, base_currency="USD",
                                        quote_currency="GHS", rate=Decimal("12"),
                                        effective_from=timezone.now() - timedelta(days=1))
        base, rate = convert_to_base(Decimal("10"), "USD", self.ch)
        self.assertEqual(base, Decimal("120.00"))

    def test_no_rate_returns_none(self):
        base, rate = convert_to_base(Decimal("10"), "EUR", self.ch)
        self.assertIsNone(base)
        self.assertIsNone(rate)

    def test_uses_most_recent_effective_rate(self):
        now = timezone.now()
        CurrencySnapshot.objects.create(church=self.ch, base_currency="USD", quote_currency="GHS",
                                        rate=Decimal("10"), effective_from=now - timedelta(days=10))
        CurrencySnapshot.objects.create(church=self.ch, base_currency="USD", quote_currency="GHS",
                                        rate=Decimal("13"), effective_from=now - timedelta(days=1))
        base, rate = convert_to_base(Decimal("1"), "USD", self.ch)
        self.assertEqual(base, Decimal("13.00"))  # the newer rate

    def test_church_rate_preferred_over_global(self):
        now = timezone.now()
        CurrencySnapshot.objects.create(church=None, base_currency="USD", quote_currency="GHS",
                                        rate=Decimal("10"), effective_from=now - timedelta(days=1))
        CurrencySnapshot.objects.create(church=self.ch, base_currency="USD", quote_currency="GHS",
                                        rate=Decimal("14"), effective_from=now - timedelta(days=1))
        base, rate = convert_to_base(Decimal("1"), "USD", self.ch)
        self.assertEqual(base, Decimal("14.00"))  # church-specific wins

    def test_global_rate_fallback(self):
        CurrencySnapshot.objects.create(church=None, base_currency="USD", quote_currency="GHS",
                                        rate=Decimal("11"), effective_from=timezone.now() - timedelta(days=1))
        base, rate = convert_to_base(Decimal("2"), "USD", self.ch)
        self.assertEqual(base, Decimal("22.00"))


class FinanceConfigAccessTests(TestCase):
    def setUp(self):
        self.ch = Church.objects.create(name="CEA", short_code="CEA", status="active")
        self.treasurer = User.objects.create_user(email="t@x.com", password="pw12345678")
        p = Profile.objects.get(user=self.treasurer)
        p.access_level = AccessLevel.TREASURER; p.church = self.ch; p.save()
        self.member_user = User.objects.create_user(email="m@x.com", password="pw12345678")
        pm = Profile.objects.get(user=self.member_user)
        pm.access_level = AccessLevel.MEMBER; pm.church = self.ch; pm.save()

    def test_treasurer_can_access_accounts(self):
        c = Client(); c.force_login(self.treasurer)
        self.assertEqual(c.get("/finance/accounts/").status_code, 200)

    def test_member_cannot_access(self):
        c = Client(); c.force_login(self.member_user)
        self.assertEqual(c.get("/finance/accounts/").status_code, 403)

    def test_create_account_writes_audit(self):
        c = Client(); c.force_login(self.treasurer)
        c.post("/finance/accounts/new/", {
            "name": "Offerings", "short_code": "OFF", "church_id": str(self.ch.id), "is_income": "on"})
        self.assertTrue(FinanceAccount.objects.filter(name="Offerings").exists())
        from audit.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(table_name="finance_accounts", action="create").exists())


class IncomeLifecycleTests(TestCase):
    def setUp(self):
        from finance.models import FinanceAccount
        from org.models import ChurchSettings
        self.ch = Church.objects.create(name="CE Accra", short_code="CEA",
                                        status="active", default_currency="GHS")
        self.account = FinanceAccount.objects.create(church=self.ch, name="Offerings",
                                                     short_code="OFF", is_income=True)
        # two treasurers (submitter + approver)
        self.sub_user = User.objects.create_user(email="sub@x.com", password="pw12345678")
        ps = Profile.objects.get(user=self.sub_user); ps.access_level = AccessLevel.TREASURER; ps.church = self.ch; ps.save()
        self.app_user = User.objects.create_user(email="app@x.com", password="pw12345678")
        pa = Profile.objects.get(user=self.app_user); pa.access_level = AccessLevel.TREASURER; pa.church = self.ch; pa.save()
        self.sub = Profile.objects.get(user=self.sub_user)
        self.app = Profile.objects.get(user=self.app_user)
        ChurchSettings.objects.create(church=self.ch, require_income_approval=True)

    def _create(self, profile=None, lines=None):
        from finance.income import create_income
        from datetime import date
        return create_income(profile=profile or self.sub, church=self.ch, account=self.account,
                             received_date=date.today(),
                             lines=lines or [{"amount": "100", "currency": "GHS"}])

    def test_create_pending_when_approval_required(self):
        rec = self._create()
        self.assertEqual(rec.status, "pending")
        self.assertEqual(rec.base_amount, Decimal("100.00"))

    def test_create_approved_when_approval_off(self):
        from org.models import ChurchSettings
        s = ChurchSettings.objects.get(church=self.ch); s.require_income_approval = False; s.save()
        rec = self._create()
        self.assertEqual(rec.status, "approved")
        self.assertIsNotNone(rec.approved_at)

    def test_submitter_cannot_approve_own(self):
        from finance.income import approve_income, IncomeError
        rec = self._create(profile=self.sub)
        with self.assertRaises(IncomeError):
            approve_income(profile=self.sub, record=rec)

    def test_another_treasurer_can_approve(self):
        from finance.income import approve_income
        rec = self._create(profile=self.sub)
        approve_income(profile=self.app, record=rec)
        rec.refresh_from_db()
        self.assertEqual(rec.status, "approved")
        self.assertEqual(rec.approved_by, self.app.pk)

    def test_reject_requires_reason(self):
        from finance.income import reject_income, IncomeError
        rec = self._create(profile=self.sub)
        with self.assertRaises(IncomeError):
            reject_income(profile=self.app, record=rec, reason="")

    def test_cannot_approve_non_pending(self):
        from finance.income import approve_income, void_income, IncomeError
        rec = self._create(profile=self.sub)
        void_income(profile=self.app, record=rec, reason="duplicate")
        with self.assertRaises(IncomeError):
            approve_income(profile=self.app, record=rec)

    def test_void_requires_reason_and_is_permanent(self):
        from finance.income import void_income, IncomeError
        rec = self._create(profile=self.sub)
        with self.assertRaises(IncomeError):
            void_income(profile=self.app, record=rec, reason="")
        void_income(profile=self.app, record=rec, reason="entered twice")
        rec.refresh_from_db()
        self.assertEqual(rec.status, "voided")
        self.assertEqual(rec.void_reason, "entered twice")

    def test_multi_currency_sums_to_base(self):
        from finance.models import CurrencySnapshot
        from django.utils import timezone
        from datetime import timedelta
        # 1 USD = 12 GHS
        CurrencySnapshot.objects.create(church=self.ch, base_currency="USD", quote_currency="GHS",
                                        rate=Decimal("12"), effective_from=timezone.now() - timedelta(days=1))
        rec = self._create(lines=[{"amount": "100", "currency": "GHS"},
                                  {"amount": "10", "currency": "USD"}])
        # 100 GHS + (10 USD * 12) = 100 + 120 = 220 GHS
        self.assertTrue(rec.is_multi_currency)
        self.assertEqual(rec.base_amount, Decimal("220.00"))
        self.assertEqual(rec.currency_amounts.count(), 2)

    def test_missing_rate_raises(self):
        from finance.income import IncomeError
        with self.assertRaises(IncomeError):
            self._create(lines=[{"amount": "10", "currency": "EUR"}])


class SupportedCurrencyTests(TestCase):
    def test_supported_set_is_the_five(self):
        from finance.enums import SUPPORTED_CURRENCY_CODES
        self.assertEqual(set(SUPPORTED_CURRENCY_CODES), {"GHS", "NGN", "USD", "EUR", "ESPEES"})

    def test_rate_board_saves_only_changed(self):
        ch = Church.objects.create(name="CEA", short_code="CEA", status="active", default_currency="GHS")
        u = User.objects.create_user(email="t2@x.com", password="pw12345678")
        p = Profile.objects.get(user=u); p.access_level = AccessLevel.TREASURER; p.church = ch; p.save()
        c = Client(); c.force_login(u)
        # save USD and ESPEES rates in one submit
        c.post("/finance/rates/save/", {"church_id": str(ch.id), "rate_USD": "12", "rate_ESPEES": "16"})
        self.assertTrue(CurrencySnapshot.objects.filter(church=ch, base_currency="USD", quote_currency="GHS", rate=Decimal("12")).exists())
        self.assertTrue(CurrencySnapshot.objects.filter(church=ch, base_currency="ESPEES", quote_currency="GHS", rate=Decimal("16")).exists())
        # re-saving the same USD rate creates no duplicate
        before = CurrencySnapshot.objects.filter(church=ch, base_currency="USD").count()
        c.post("/finance/rates/save/", {"church_id": str(ch.id), "rate_USD": "12"})
        self.assertEqual(CurrencySnapshot.objects.filter(church=ch, base_currency="USD").count(), before)

    def test_income_rejects_unsupported_currency(self):
        from finance.models import FinanceAccount
        ch = Church.objects.create(name="CEB", short_code="CEB", status="active", default_currency="GHS")
        acct = FinanceAccount.objects.create(church=ch, name="Off", short_code="OFF", is_income=True)
        u = User.objects.create_user(email="t3@x.com", password="pw12345678")
        p = Profile.objects.get(user=u); p.access_level = AccessLevel.TREASURER; p.church = ch; p.save()
        c = Client(); c.force_login(u)
        from finance.models import IncomeRecord
        c.post("/finance/income/new/", {
            "church_id": str(ch.id), "account_id": str(acct.id), "received_date": "2026-06-12",
            "amount_0": "100", "currency_0": "XYZ"})
        self.assertFalse(IncomeRecord.objects.filter(church=ch).exists())


class EspeesDisplayTests(TestCase):
    def setUp(self):
        from finance.models import FinanceAccount, CurrencySnapshot
        from django.utils import timezone
        from datetime import timedelta
        self.ch = Church.objects.create(name="CE Accra", short_code="CEA",
                                        status="active", default_currency="GHS")
        self.account = FinanceAccount.objects.create(church=self.ch, name="Off", short_code="OFF", is_income=True)
        u = User.objects.create_user(email="t@x.com", password="pw12345678")
        p = Profile.objects.get(user=u); p.access_level = AccessLevel.TREASURER; p.church = self.ch; p.save()
        self.prof = Profile.objects.get(user=u)
        # 1 ESPEES = 16 GHS  => to get ESPEES from GHS, multiply by (1/16). We store
        # the snapshot so convert_to_espees finds ESPEES->GHS and inverts.
        CurrencySnapshot.objects.create(church=self.ch, base_currency="ESPEES", quote_currency="GHS",
                                        rate=Decimal("16"), effective_from=timezone.now() - timedelta(days=1))

    def _create(self, amount="160"):
        from finance.income import create_income
        from datetime import date
        return create_income(profile=self.prof, church=self.ch, account=self.account,
                             received_date=date.today(), lines=[{"amount": amount, "currency": "GHS"}])

    def test_espees_frozen_on_create(self):
        rec = self._create("160")  # 160 GHS / 16 = 10 ESPEES
        self.assertEqual(rec.base_amount, Decimal("160.00"))
        self.assertEqual(rec.espees_amount, Decimal("10.00"))

    def test_espees_null_when_no_rate(self):
        from finance.models import CurrencySnapshot
        CurrencySnapshot.objects.all().delete()
        rec = self._create("100")
        self.assertEqual(rec.base_amount, Decimal("100.00"))
        self.assertIsNone(rec.espees_amount)

    def test_espees_frozen_value_unaffected_by_later_rate_change(self):
        from finance.models import CurrencySnapshot
        from django.utils import timezone
        rec = self._create("160")
        self.assertEqual(rec.espees_amount, Decimal("10.00"))
        # rate changes later
        CurrencySnapshot.objects.create(church=self.ch, base_currency="ESPEES", quote_currency="GHS",
                                        rate=Decimal("20"), effective_from=timezone.now())
        rec.refresh_from_db()
        self.assertEqual(rec.espees_amount, Decimal("10.00"))  # unchanged — frozen

    def test_money_tag_renders_both(self):
        from finance.templatetags.money import money
        html = str(money(Decimal("160.00"), "GHS", Decimal("10.00")))
        self.assertIn("160.00 GHS", html)
        self.assertIn("10.00 ESPEES", html)

    def test_money_tag_no_redundant_line_when_base_is_espees(self):
        from finance.templatetags.money import money
        html = str(money(Decimal("10.00"), "ESPEES", Decimal("10.00")))
        self.assertIn("10.00 ESPEES", html)
        self.assertNotIn("≈", html)  # no second equivalent line


class RateDisplayTests(TestCase):
    def test_clean_rate_shows_2dp(self):
        from finance.templatetags.money import rate_display
        from decimal import Decimal
        self.assertEqual(rate_display(Decimal("12.000000")), "12.00")
        self.assertEqual(rate_display(Decimal("8.5")), "8.50")
        self.assertEqual(rate_display(Decimal("101.80")), "101.80")

    def test_small_rate_keeps_full_precision(self):
        from finance.templatetags.money import rate_display
        from decimal import Decimal
        # 0.0098 would wrongly become 0.01 at 2dp -> must show full
        self.assertEqual(rate_display(Decimal("0.0098")), "0.0098")
        self.assertEqual(rate_display(Decimal("0.062500")), "0.0625")

    def test_none_and_zero(self):
        from finance.templatetags.money import rate_display
        from decimal import Decimal
        self.assertEqual(rate_display(None), "—")
        self.assertEqual(rate_display(Decimal("0.00")), "0.00")


class SelfApprovalTests(TestCase):
    def setUp(self):
        from finance.models import FinanceAccount
        from org.models import ChurchSettings
        self.ch = Church.objects.create(name="CE Solo", short_code="CES",
                                        status="active", default_currency="GHS")
        self.account = FinanceAccount.objects.create(church=self.ch, name="Off", short_code="OFF", is_income=True)
        u = User.objects.create_user(email="solo@x.com", password="pw12345678")
        p = Profile.objects.get(user=u); p.access_level = AccessLevel.TREASURER; p.church = self.ch; p.save()
        self.solo = Profile.objects.get(user=u)
        self.settings = ChurchSettings.objects.create(church=self.ch, require_income_approval=True,
                                                      allow_self_approval=False)

    def _create(self):
        from finance.income import create_income
        from datetime import date
        return create_income(profile=self.solo, church=self.ch, account=self.account,
                             received_date=date.today(), lines=[{"amount": "100", "currency": "GHS"}])

    def test_self_approval_blocked_by_default(self):
        from finance.income import approve_income, IncomeError
        rec = self._create()
        with self.assertRaises(IncomeError):
            approve_income(profile=self.solo, record=rec)

    def test_self_approval_allowed_when_enabled(self):
        from finance.income import approve_income
        self.settings.allow_self_approval = True; self.settings.save()
        rec = self._create()
        approve_income(profile=self.solo, record=rec)  # should NOT raise
        rec.refresh_from_db()
        self.assertEqual(rec.status, "approved")
        self.assertEqual(rec.approved_by, self.solo.pk)


class EspeesLiveFallbackTests(TestCase):
    def setUp(self):
        from finance.models import FinanceAccount
        self.ch = Church.objects.create(name="CE Live", short_code="CEL",
                                        status="active", default_currency="NGN")
        u = User.objects.create_user(email="lf@x.com", password="pw12345678")
        p = Profile.objects.get(user=u); p.access_level = AccessLevel.TREASURER; p.church = self.ch; p.save()

    def test_live_estimate_when_frozen_null_and_rate_exists(self):
        from finance.models import CurrencySnapshot
        from finance.templatetags.money import money
        from django.utils import timezone
        from datetime import timedelta
        # rate exists now
        CurrencySnapshot.objects.create(church=self.ch, base_currency="ESPEES", quote_currency="NGN",
                                        rate=Decimal("2050"), effective_from=timezone.now() - timedelta(days=1))
        html = str(money(Decimal("12603805.00"), "NGN", None, self.ch))
        self.assertIn("ESPEES", html)
        self.assertIn("today's rate", html)   # marked as estimate
        self.assertIn("6,148.20", html)        # 12603805 / 2050

    def test_frozen_value_not_marked_as_estimate(self):
        from finance.templatetags.money import money
        html = str(money(Decimal("980.00"), "GHS", Decimal("61.25"), self.ch))
        self.assertIn("61.25", html)
        self.assertNotIn("today's rate", html)  # frozen = no estimate marker

    def test_dash_when_no_rate_at_all(self):
        from finance.templatetags.money import money
        html = str(money(Decimal("100.00"), "NGN", None, self.ch))
        self.assertIn("ESPEES —", html)         # no rate -> honest dash
