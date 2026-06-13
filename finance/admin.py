from django.contrib import admin
from .models import FinanceAccount, FinanceCategory, CurrencySnapshot


@admin.register(FinanceAccount)
class FinanceAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "church", "is_income", "display_order", "archived_at")
    list_filter = ("is_income",)


@admin.register(FinanceCategory)
class FinanceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "account", "display_order", "archived_at")


@admin.register(CurrencySnapshot)
class CurrencySnapshotAdmin(admin.ModelAdmin):
    list_display = ("base_currency", "quote_currency", "rate", "effective_from", "church")
    list_filter = ("base_currency", "quote_currency")


