from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User, Member, Profile


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "phone", "is_active", "is_staff", "date_joined")
    search_fields = ("email", "phone")
    ordering = ("-date_joined",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("member_code", "surname", "other_names", "church", "is_active")
    search_fields = ("member_code", "surname", "other_names", "phone_primary", "email")
    list_filter = ("is_active", "gender", "marital_status")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "access_level", "member", "church", "is_locked")
    list_filter = ("access_level", "is_locked")


from .models import PhoneOtp


@admin.register(PhoneOtp)
class PhoneOtpAdmin(admin.ModelAdmin):
    list_display = ("phone", "purpose", "status", "attempts", "expires_at", "created_at")
    list_filter = ("status", "purpose")
    search_fields = ("phone",)
