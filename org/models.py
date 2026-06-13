"""
Organisational hierarchy: ecclesiastical units (zone/group tree), churches, and
the placement tables (ministry group / department / fellowship / cell).

This is the minimal set needed so accounts.Member and accounts.Profile FKs
resolve and the project migrates. Remaining columns/tables are added as each
feature area is ported; the field set here matches the live schema export.
"""
import uuid
from django.db import models
from accounts.enums import ChurchStatus, EcclesiasticalUnitType


class EcclesiasticalUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    unit_type = models.CharField(max_length=20, choices=EcclesiasticalUnitType.choices)
    parent_unit = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="children", db_column="parent_unit_id",
    )
    name = models.TextField()
    short_code = models.TextField()
    display_order = models.IntegerField(default=0)
    head_church = models.ForeignKey(
        "Church", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="heads_units", db_column="head_church_id",
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ecclesiastical_units"

    def __str__(self):
        return f"{self.name} ({self.unit_type})"


class Church(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    short_code = models.TextField()
    display_name = models.TextField(null=True, blank=True)
    member_id_template = models.TextField(default="{CHURCH_CODE}-{YEAR}-{SEQ:00000}")
    default_currency = models.TextField(default="GHS")
    timezone = models.TextField(default="Africa/Accra")
    city = models.TextField(null=True, blank=True)
    parent_unit = models.ForeignKey(
        EcclesiasticalUnit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="churches", db_column="parent_unit_id",
    )
    planted_from_church = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="plants", db_column="planted_from_church_id",
    )
    planted_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=ChurchStatus.choices, default=ChurchStatus.INACTIVE
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "churches"
        verbose_name_plural = "churches"

    def __str__(self):
        return self.display_name or self.name


class MinistryGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE,
                               related_name="ministry_groups", db_column="church_id")
    name = models.TextField()
    short_code = models.TextField()
    display_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ministry_groups"


class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE,
                               related_name="departments", db_column="church_id")
    parent_department = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="children", db_column="parent_department_id",
    )
    name = models.TextField()
    short_code = models.TextField()
    description = models.TextField(null=True, blank=True)
    display_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "departments"

    def __str__(self):
        return self.name


class Fellowship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE,
                               related_name="fellowships", db_column="church_id")
    parent_department = models.ForeignKey(
        Department, on_delete=models.CASCADE,
        related_name="fellowships", db_column="parent_department_id",
    )
    name = models.TextField()
    short_code = models.TextField()
    description = models.TextField(null=True, blank=True)
    meeting_day = models.TextField(null=True, blank=True)
    meeting_time = models.TimeField(null=True, blank=True)
    display_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fellowships"

    def __str__(self):
        return self.name


class Cell(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fellowship = models.ForeignKey(
        Fellowship, on_delete=models.CASCADE, related_name="cells",
        db_column="fellowship_id",
    )
    name = models.TextField()
    short_code = models.TextField()
    location_description = models.TextField(null=True, blank=True)
    meeting_day = models.TextField(null=True, blank=True)
    meeting_time = models.TimeField(null=True, blank=True)
    display_order = models.IntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cells"

    def __str__(self):
        return self.name
class ChurchSettings(models.Model):
    """Per-church configuration — faithful port of the original church_settings
    table (one home for all church config). Comms/SMTP fields are present but
    dormant until the Comms domain is built; finance fields are active now.
    """
    church = models.OneToOneField(Church, on_delete=models.CASCADE,
                                  primary_key=True, related_name="settings",
                                  db_column="church_id")
    # --- comms (dormant until Comms is built) ---
    sms_api_key = models.TextField(null=True, blank=True)
    sms_sender_id = models.TextField(null=True, blank=True)
    sms_dev_mode = models.BooleanField(null=True, blank=True)
    smtp_host = models.TextField(null=True, blank=True)
    smtp_port = models.IntegerField(null=True, blank=True)
    smtp_user = models.TextField(null=True, blank=True)
    smtp_password = models.TextField(null=True, blank=True)
    smtp_from_email = models.TextField(null=True, blank=True)
    smtp_from_name = models.TextField(null=True, blank=True)
    smtp_secure = models.BooleanField(null=True, blank=True)
    # --- finance (active now) ---
    require_income_approval = models.BooleanField(null=True, blank=True, default=True)
    # When True, the recorder may approve their own income (for churches/groups
    # with a single treasurer). Default False keeps separation of duties.
    allow_self_approval = models.BooleanField(null=True, blank=True, default=False)
    display_currencies = models.JSONField(null=True, blank=True, default=list)
    # --- audit ---
    updated_at = models.DateTimeField(auto_now=True)
    updated_by_member_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "church_settings"

    def __str__(self):
        return f"Settings for {self.church_id}"
