from django.contrib import admin
from .models import Household, HouseholdMember, FamilyRelationship, MemberSpouseLink


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("name", "church", "head_member")
    search_fields = ("name",)
    raw_id_fields = ("head_member",)


@admin.register(HouseholdMember)
class HouseholdMemberAdmin(admin.ModelAdmin):
    list_display = ("household", "member", "relationship_to_head", "is_primary")
    list_filter = ("relationship_to_head",)
    raw_id_fields = ("household", "member")


@admin.register(FamilyRelationship)
class FamilyRelationshipAdmin(admin.ModelAdmin):
    list_display = ("from_member", "type", "to_member", "parent_type")
    list_filter = ("type",)
    raw_id_fields = ("from_member", "to_member")


@admin.register(MemberSpouseLink)
class MemberSpouseLinkAdmin(admin.ModelAdmin):
    list_display = ("member_a", "member_b", "marriage_date", "is_current")
    raw_id_fields = ("member_a", "member_b")
