"""
Finance foundation: accounts, categories, currency snapshots, and per-church
finance settings. No transactions here — this is the structure income/expense
records will reference. Faithful ports of the Supabase finance schema.
"""
import uuid
from django.db import models


class FinanceAccount(models.Model):
    """A top-level money bucket, either income or expense (is_income)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("org.Church", on_delete=models.CASCADE,
                               related_name="finance_accounts", db_column="church_id")
    name = models.TextField()
    short_code = models.TextField()
    is_income = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "finance_accounts"
        ordering = ["display_order", "name"]

    def __str__(self):
        return f"{self.name} ({'income' if self.is_income else 'expense'})"


class FinanceCategory(models.Model):
    """A sub-bucket under an account (e.g. 'Tithes' under 'Offerings')."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(FinanceAccount, on_delete=models.CASCADE,
                                related_name="categories", db_column="account_id")
    name = models.TextField()
    short_code = models.TextField()
    display_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "finance_categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class CurrencySnapshot(models.Model):
    """A directional exchange rate (base -> quote) effective from a date.
    Income/expense conversion looks up the applicable snapshot by date + scope."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("org.Church", on_delete=models.CASCADE, null=True, blank=True,
                               related_name="currency_snapshots", db_column="church_id")
    base_currency = models.TextField()      # e.g. GHS
    quote_currency = models.TextField()     # e.g. USD
    rate = models.DecimalField(max_digits=18, decimal_places=6)  # 1 base = rate quote
    effective_from = models.DateTimeField()
    source = models.TextField(null=True, blank=True)
    zone_unit_id = models.UUIDField(null=True, blank=True)
    created_by = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "currency_snapshots"
        ordering = ["-effective_from"]
        indexes = [
            models.Index(fields=["church", "base_currency", "quote_currency", "-effective_from"]),
        ]

    def __str__(self):
        return f"{self.base_currency}->{self.quote_currency} @ {self.rate} ({self.effective_from:%Y-%m-%d})"


class IncomeRecord(models.Model):
    """A recorded income entry (offering, tithe, partnership, etc.) moving
    through the pending -> approved/rejected -> voided lifecycle. Faithful port
    of income_records. base_amount/exchange_rate are the church-base conversion;
    for multi-currency records the base_amount is the sum of the child amounts."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("org.Church", on_delete=models.CASCADE,
                               related_name="income_records", db_column="church_id")
    # where collected
    collected_at_church = models.BooleanField(default=True)
    collected_at_unit_type = models.CharField(max_length=20, null=True, blank=True)
    collected_at_department = models.ForeignKey("org.Department", on_delete=models.SET_NULL,
                                                null=True, blank=True, db_column="collected_at_department_id",
                                                related_name="+")
    collected_at_fellowship = models.ForeignKey("org.Fellowship", on_delete=models.SET_NULL,
                                                null=True, blank=True, db_column="collected_at_fellowship_id",
                                                related_name="+")
    collected_at_cell = models.ForeignKey("org.Cell", on_delete=models.SET_NULL,
                                          null=True, blank=True, db_column="collected_at_cell_id",
                                          related_name="+")
    # classification + links
    account = models.ForeignKey(FinanceAccount, on_delete=models.PROTECT,
                                related_name="income_records", db_column="account_id")
    category = models.ForeignKey(FinanceCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="income_records", db_column="category_id")
    member = models.ForeignKey("accounts.Member", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="income_records", db_column="member_id")
    pledge_id = models.UUIDField(null=True, blank=True)  # linked in slice 4
    # money
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.TextField()
    base_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    # ESPEES equivalent, frozen at transaction time (universal reference lens).
    # NET-NEW vs Supabase: stored so it never changes retroactively. Null if no
    # ESPEES rate was available on the received date.
    espees_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    received_date = models.DateField()
    payment_method = models.TextField(null=True, blank=True)
    reference_number = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    is_multi_currency = models.BooleanField(default=False)  # NET-NEW convenience flag
    # lifecycle
    status = models.CharField(max_length=20, default="pending")
    submitted_by = models.UUIDField(null=True, blank=True)
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    voided_by = models.UUIDField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "income_records"
        ordering = ["-received_date", "-created_at"]
        indexes = [
            models.Index(fields=["church", "status"]),
            models.Index(fields=["account", "received_date"]),
        ]

    def __str__(self):
        return f"{self.amount} {self.currency} — {self.account.name} ({self.status})"


class IncomeCurrencyAmount(models.Model):
    """A single currency line within a multi-currency income record. The parent's
    base_amount is the sum of each line converted at its captured rate."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    income_record = models.ForeignKey(IncomeRecord, on_delete=models.CASCADE,
                                      related_name="currency_amounts", db_column="income_record_id")
    currency = models.TextField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    rate = models.DecimalField(max_digits=18, decimal_places=6)  # multiplier to base
    rate_effective_from = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "income_currency_amounts"

    def __str__(self):
        return f"{self.amount} {self.currency}"
