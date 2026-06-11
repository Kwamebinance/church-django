"""
Authorization tables, ported from the live schema.

  - Role         : a named role within a church, with is_leader + announce perms.
  - Assignment   : a member holds a role within a specific unit (cell/fellowship/
                   department), with start/end dates. end_date IS NULL = active.
                   This drives sub-church "leader of this unit" narrowing (Layer 2).
  - MemberRole   : a member has an access_level at a scope (church/group/zone).
                   This drives church-level reach (Layer 1) via reach_churches().

Note the two are distinct, matching the live system:
  * MemberRole.scope_type is one of 'church' / 'group' / 'zone' (NOT cell/fellowship)
    and scope_id is that unit's id. It determines which CHURCHES you reach.
  * Assignment pins you to an actual cell/fellowship/department and, combined with
    Role.is_leader, determines which UNIT you lead inside a church.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("org.Church", on_delete=models.CASCADE,
                               related_name="roles", db_column="church_id")
    name = models.TextField()
    is_leader = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    # announcement permission flags (used by can_post/see_announcement later)
    can_announce_own_cell = models.BooleanField(default=False)
    can_announce_own_fellowship = models.BooleanField(default=False)
    can_announce_own_department = models.BooleanField(default=False)
    can_announce_any_cell = models.BooleanField(default=False)
    can_announce_any_fellowship = models.BooleanField(default=False)
    can_announce_any_department = models.BooleanField(default=False)
    can_announce_whole_church = models.BooleanField(default=False)
    can_announce_leaders_only = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roles"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Assignment(models.Model):
    """A member holds a role within a unit. Active when end_date is null."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                               related_name="assignments", db_column="member_id")
    role = models.ForeignKey(Role, on_delete=models.PROTECT,
                             related_name="assignments", db_column="role_id")
    department = models.ForeignKey("org.Department", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="assignments",
                                   db_column="department_id")
    fellowship = models.ForeignKey("org.Fellowship", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="assignments",
                                   db_column="fellowship_id")
    cell = models.ForeignKey("org.Cell", on_delete=models.SET_NULL,
                             null=True, blank=True, related_name="assignments",
                             db_column="cell_id")
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)  # null = active
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assignments"

    def __str__(self):
        return f"{self.member} as {self.role}"


class MemberRole(models.Model):
    """A member's access_level at a scope. Drives church-level reach.

    scope_type in ('church','group','zone'); scope_id is that unit's id.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey("accounts.Member", on_delete=models.CASCADE,
                               related_name="member_roles", db_column="member_id")
    level = models.CharField(max_length=20)  # access_level enum value
    scope_type = models.TextField()           # 'church' | 'group' | 'zone'
    scope_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, db_column="created_by")

    class Meta:
        db_table = "member_roles"

    def __str__(self):
        return f"{self.member} {self.level}@{self.scope_type}"
