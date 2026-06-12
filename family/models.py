"""
Family / household domain models. Faithful port of the Supabase schema. Models
only for now (Phase C builds the UI); the seeder populates these immediately.

Enums (from the real pg_enums):
  household_role:           head, spouse, child, parent, sibling, grandchild, dependent, other
  family_relationship_type: parent_of, spouse_of
  family_parent_type:       biological, adoptive, step
  family_end_reason:        divorced, widowed, annulled
"""
import uuid
from datetime import date
from django.db import models


class HouseholdRole(models.TextChoices):
    HEAD = "head", "Head"
    SPOUSE = "spouse", "Spouse"
    CHILD = "child", "Child"
    PARENT = "parent", "Parent"
    SIBLING = "sibling", "Sibling"
    GRANDCHILD = "grandchild", "Grandchild"
    DEPENDENT = "dependent", "Dependent"
    OTHER = "other", "Other"


class FamilyRelationshipType(models.TextChoices):
    PARENT_OF = "parent_of", "Parent of"
    SPOUSE_OF = "spouse_of", "Spouse of"


class FamilyParentType(models.TextChoices):
    BIOLOGICAL = "biological", "Biological"
    ADOPTIVE = "adoptive", "Adoptive"
    STEP = "step", "Step"


class FamilyEndReason(models.TextChoices):
    DIVORCED = "divorced", "Divorced"
    WIDOWED = "widowed", "Widowed"
    ANNULLED = "annulled", "Annulled"


class Household(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("org.Church", on_delete=models.CASCADE,
                               related_name="households", db_column="church_id")
    name = models.TextField()
    head_member = models.ForeignKey("accounts.Member", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="heads_households",
                                    db_column="head_member_id")
    notes = models.TextField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "households"
        ordering = ["name"]

    def __str__(self):
        return self.name


class HouseholdMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    household = models.ForeignKey(Household, on_delete=models.CASCADE,
                                  related_name="members", db_column="household_id")
    member = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                               related_name="household_memberships", db_column="member_id")
    relationship_to_head = models.CharField(max_length=20, choices=HouseholdRole.choices)
    is_primary = models.BooleanField(default=False)
    start_date = models.DateField(default=date.today)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "household_members"

    def __str__(self):
        return f"{self.member} ({self.relationship_to_head})"


class FamilyRelationship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=FamilyRelationshipType.choices)
    from_member = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                                    related_name="relationships_from", db_column="from_member_id")
    to_member = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                                  related_name="relationships_to", db_column="to_member_id")
    parent_type = models.CharField(max_length=20, choices=FamilyParentType.choices,
                                   null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    end_reason = models.CharField(max_length=20, choices=FamilyEndReason.choices,
                                  null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "family_relationships"

    def __str__(self):
        return f"{self.from_member} {self.type} {self.to_member}"


class MemberSpouseLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member_a = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                                 related_name="spouse_links_a", db_column="member_a_id")
    member_b = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                                 related_name="spouse_links_b", db_column="member_b_id")
    marriage_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "member_spouse_links"

    def __str__(self):
        return f"{self.member_a} ⚭ {self.member_b}"
