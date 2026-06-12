"""
Enum (choices) definitions, ported verbatim from the live PostgreSQL enum types
exported on 2026-06-10. Values match the database labels exactly so migrated data
maps cleanly. Do NOT rename values without a data migration.

Access-level ordering note:
    Authority ranking follows the LIVE has_access_at_least() function, NOT the
    pg_enum sort order. The real ladder (highest to lowest) is:
        zonal_pastor > group_pastor > church_pastor > admin > treasurer
        > unit_leader > counter > member
    with super_admin as an always-passes override above all. ACCESS_RANK below
    encodes this. (An earlier version mistakenly used the enum sort order, which
    put church_pastor above super_admin -- corrected in the scope-walk slice.)
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
    SUPER_ADMIN = "super_admin", "System Administrator"
    CHURCH_PASTOR = "church_pastor", "Church pastor"


# Numeric rank matching the LIVE has_access_at_least() ladder exactly.
# super_admin is handled as an always-passes override in has_at_least(), but we
# also give it the top numeric value so direct rank comparisons behave.
# Live ladder: zonal_pastor=8, group_pastor=7, church_pastor=6, admin=5,
#              treasurer=4, unit_leader=3, counter=2, member=1.
ACCESS_RANK = {
    AccessLevel.MEMBER: 1,
    AccessLevel.COUNTER: 2,
    AccessLevel.UNIT_LEADER: 3,
    AccessLevel.TREASURER: 4,
    AccessLevel.ADMIN: 5,
    AccessLevel.CHURCH_PASTOR: 6,
    AccessLevel.GROUP_PASTOR: 7,
    AccessLevel.ZONAL_PASTOR: 8,
    AccessLevel.SUPER_ADMIN: 99,
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
