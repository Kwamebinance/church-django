from django.contrib import admin
from .models import BirthdayCardTemplate


@admin.register(BirthdayCardTemplate)
class BirthdayCardTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "church", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
