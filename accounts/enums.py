"""
Enum (choices) definitions, ported verbatim from the live PostgreSQL enum types
exported on 2026-06-10. Values match the database labels exactly so migrated data
maps cleanly. Do NOT rename values without a data migration.

Access-level ordering note:
    The access_level enum does NOT sort as a clean 1..9 sequence. Its real
    pg_enum sort order is:
        member(1) counter(2) unit_leader(3) treasurer(4) admin(5)
        group_pastor(5.5) zonal_pastor(5.75) super_admin(6) church_pastor(7)
    so church_pastor sorts HIGHEST (above super_admin) and the pastor tiers are
    wedged between admin and super_admin. ACCESS_RANK below encodes this exactly.
    All "has at least" comparisons must use ACCESS_RANK, never list position.
"""
from django.db import models


class AccessLevel(models.TextChoices):
    MEMBER = "member", "Member"
    COUNTER = "counter", "Counter"
    UNIT_LEADER = "unit_leader", "Unit leader"
    TREASURER = "treasurer", "Treasurer"
    ADMIN = "admin", "Admin"
    GROUP_PASTOR = "group_pastor", "Group pastor"
    ZONAL_PASTOR = "zonal_pastor", "Zonal pastor"
    SUPER_ADMIN = "super_admin", "Super admin"
    CHURCH_PASTOR = "church_pastor", "Church pastor"


# Numeric rank from the real pg_enum sort order. Used by has_at_least().
# Higher number = more authority.
ACCESS_RANK = {
    AccessLevel.MEMBER: 1.0,
    AccessLevel.COUNTER: 2.0,
    AccessLevel.UNIT_LEADER: 3.0,
    AccessLevel.TREASURER: 4.0,
    AccessLevel.ADMIN: 5.0,
    AccessLevel.GROUP_PASTOR: 5.5,
    AccessLevel.ZONAL_PASTOR: 5.75,
    AccessLevel.SUPER_ADMIN: 6.0,
    AccessLevel.CHURCH_PASTOR: 7.0,
}


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"


class MaritalStatus(models.TextChoices):
    SINGLE = "single", "Single"
    MARRIED = "married", "Married"
    DIVORCED = "divorced", "Divorced"
    WIDOWED = "widowed", "Widowed"
    SEPARATED = "separated", "Separated"


class BaptismStatus(models.TextChoices):
    NOT_BAPTIZED = "not_baptized", "Not baptized"
    BAPTIZED_WATER = "baptized_water", "Baptized (water)"
    BAPTIZED_HOLY_SPIRIT = "baptized_holy_spirit", "Baptized (Holy Spirit)"
    BOTH = "both", "Both"


class FoundationSchoolStatus(models.TextChoices):
    NOT_ENROLLED = "not_enrolled", "Not enrolled"
    ENROLLED = "enrolled", "Enrolled"
    COMPLETED = "completed", "Completed"


class ChurchStatus(models.TextChoices):
    INACTIVE = "inactive", "Inactive"
    ACTIVE = "active", "Active"


class EcclesiasticalUnitType(models.TextChoices):
    ZONE = "zone", "Zone"
    GROUP = "group", "Group"


class OtpPurpose(models.TextChoices):
    # NOTE: the enum export appeared truncated at otp_purpose (only 'register'
    # was returned). Add the remaining labels here once the full enum list is
    # re-pulled. 'register' is confirmed.
    REGISTER = "register", "Register"


class OtpStatus(models.TextChoices):
    # Confirmed default is 'pending'; re-pull pg_enum for the full label set.
    PENDING = "pending", "Pending"
    VERIFIED = "verified", "Verified"
    CONSUMED = "consumed", "Consumed"
    EXPIRED = "expired", "Expired"
