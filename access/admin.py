from django.contrib import admin
from .models import Role, Assignment, MemberRole


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "church", "is_leader", "display_order")
    list_filter = ("is_leader",)
    search_fields = ("name",)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("member", "role", "cell", "fellowship", "department", "start_date", "end_date")
    list_filter = ("role",)
    search_fields = ("member__surname", "member__other_names")
    raw_id_fields = ("member",)


@admin.register(MemberRole)
class MemberRoleAdmin(admin.ModelAdmin):
    list_display = ("member", "level", "scope_type", "scope_id")
    list_filter = ("level", "scope_type")
    search_fields = ("member__surname", "member__other_names")
    raw_id_fields = ("member",)
