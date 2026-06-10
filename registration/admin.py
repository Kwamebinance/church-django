from django.contrib import admin
from .models import RegistrationWindow, RegistrationRequest


@admin.register(RegistrationWindow)
class RegistrationWindowAdmin(admin.ModelAdmin):
    list_display = ("is_open", "opens_at", "closes_at", "updated_at")


@admin.register(RegistrationRequest)
class RegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ("member", "cell", "church", "status", "created_at", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("member__surname", "member__other_names")
