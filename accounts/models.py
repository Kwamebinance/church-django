"""
accounts app: custom User, Profile, Member, and the access-control primitives.

The profiles/members split is the most important structural fact in the system:
  - User    = an auth/login identity (replaces Supabase auth.users).
  - Member  = a person in the church directory.
  - Profile = links a User to (optionally) a Member, plus access_level + church.
  - The super_admin account is MEMBERLESS (profile.member is None). Every scope
    derivation must tolerate member=None; reach_church_ids() does this once.
"""
import uuid
from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin, BaseUserManager,
)
from django.db import models

from .enums import (
    AccessLevel, ACCESS_RANK, Gender, MaritalStatus,
    BaptismStatus, FoundationSchoolStatus,
)


# ==========================================================================
# Custom auth user (replaces Supabase auth.users)
# ==========================================================================
class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email=None, phone=None, password=None, **extra):
        if not email and not phone:
            raise ValueError("A user must have either an email or a phone.")
        email = self.normalize_email(email) if email else None
        user = self.model(email=email, phone=phone, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # OTP-only accounts
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, phone=None, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email=email, phone=phone, password=password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    # On migration each id is set to the OLD profiles.id so links stay valid.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, null=True, blank=True)  # login field; unique
    phone = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin access (super_admin only)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    # Log in with email. Phone/OTP login is handled by a separate custom backend
    # in the auth phase; it does not need to be the USERNAME_FIELD.
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []   # email is the USERNAME_FIELD, so it's already required

    class Meta:
        db_table = "auth_user_custom"

    def __str__(self):
        return self.email or self.phone or str(self.id)


# ==========================================================================
# Member (church directory) -- abridged to confirmed columns
# ==========================================================================
class Member(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "org.Church", on_delete=models.PROTECT, related_name="members",
        db_column="church_id",
    )
    member_code = models.TextField()

    title = models.TextField(null=True, blank=True)
    surname = models.TextField()
    other_names = models.TextField()
    preferred_name = models.TextField(null=True, blank=True)
    academic_title = models.TextField(null=True, blank=True)
    maiden_name = models.TextField(null=True, blank=True)

    gender = models.CharField(max_length=10, choices=Gender.choices, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    marital_status = models.CharField(
        max_length=20, choices=MaritalStatus.choices, null=True, blank=True
    )

    phone_primary = models.TextField(null=True, blank=True)
    phone_whatsapp = models.TextField(null=True, blank=True)
    telegram_username = models.TextField(null=True, blank=True)
    email = models.TextField(null=True, blank=True)

    address = models.TextField(null=True, blank=True)
    city = models.TextField(null=True, blank=True)
    country = models.TextField(null=True, blank=True, default="Ghana")

    occupation = models.TextField(null=True, blank=True)
    employer = models.TextField(null=True, blank=True)

    baptism_status = models.CharField(
        max_length=30, choices=BaptismStatus.choices,
        null=True, blank=True, default=BaptismStatus.NOT_BAPTIZED,
    )
    born_again_date = models.DateField(null=True, blank=True)
    foundation_school_status = models.CharField(
        max_length=20, choices=FoundationSchoolStatus.choices,
        default=FoundationSchoolStatus.NOT_ENROLLED,
    )
    foundation_school_completion_date = models.DateField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)

    # Placement: a member belongs to a cell directly (NOT inferred from assignments).
    cell = models.ForeignKey(
        "org.Cell", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="members", db_column="cell_id",
    )
    ministry_group = models.ForeignKey(
        "org.MinistryGroup", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="members", db_column="ministry_group_id",
    )

    official_photo_path = models.TextField(null=True, blank=True)
    display_photo_path = models.TextField(null=True, blank=True)
    official_photo_updated_at = models.DateTimeField(null=True, blank=True)
    display_photo_updated_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    inactive_reason = models.TextField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "members"

    def __str__(self):
        return f"{self.surname} {self.other_names}".strip()


# ==========================================================================
# Profile (login account; one-to-one with the auth user)
# ==========================================================================
class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        primary_key=True, related_name="profile", db_column="id",
    )
    member = models.ForeignKey(  # NULLABLE: super_admin has no member
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="profiles", db_column="member_id",
    )
    access_level = models.CharField(
        max_length=20, choices=AccessLevel.choices, default=AccessLevel.MEMBER,
    )
    church = models.ForeignKey(
        "org.Church", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="profiles", db_column="church_id",
    )
    preferred_language = models.TextField(null=True, blank=True, default="en")
    last_login_at = models.DateTimeField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)
    locked_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "profiles"

    def __str__(self):
        return f"{self.access_level} ({self.user_id})"


# ==========================================================================
# Access-control primitives (blueprint section 3.1)
# ==========================================================================
def has_at_least(profile, level):
    """True if the profile's access_level ranks at or above `level`."""
    if profile is None:
        return False
    try:
        return ACCESS_RANK[profile.access_level] >= ACCESS_RANK[level]
    except KeyError:
        return False


def current_member_id(profile):
    """The logged-in user's member id, or None for the memberless super_admin."""
    return profile.member_id if profile else None


def reach_church_ids(profile):
    """
    Church ids the user may act across.
      - super_admin -> None  (caller treats None as 'all active churches')
      - others -> a concrete set.

    The full pastor/leader derivation (member_roles scope walked up the unit
    tree) is built in the access phase. Interim: super_admin = all; everyone
    else = their own church.
    """
    if profile is None:
        return set()
    if profile.access_level == AccessLevel.SUPER_ADMIN:
        return None  # unrestricted
    if profile.church_id:
        return {profile.church_id}
    if profile.member_id and profile.member and profile.member.church_id:
        return {profile.member.church_id}
    return set()


def member_in_reach(profile, member_id):
    """True if that member's church is within the user's reach."""
    reach = reach_church_ids(profile)
    if reach is None:
        return True  # super_admin
    return Member.objects.filter(id=member_id, church_id__in=reach).exists()


# ==========================================================================
# Phone OTP (ports the phone_otps table). Used by phone/OTP login.
# ==========================================================================
import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
from .enums import OtpPurpose, OtpStatus


class PhoneOtp(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.TextField()
    purpose = models.CharField(max_length=20, choices=OtpPurpose.choices)
    code_hash = models.TextField()          # never store the raw code
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=5)
    status = models.CharField(max_length=20, choices=OtpStatus.choices,
                              default=OtpStatus.PENDING)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.TextField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "phone_otps"

    # --- helpers ---
    @staticmethod
    def _hash(code):
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def issue(cls, phone, purpose=OtpPurpose.REGISTER, ttl_minutes=10,
              ip_address=None, user_agent=None):
        """Create a new OTP, returning (otp, raw_code). Caller sends raw_code."""
        code = f"{secrets.randbelow(1000000):06d}"   # 6-digit
        otp = cls.objects.create(
            phone=phone, purpose=purpose, code_hash=cls._hash(code),
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
            ip_address=ip_address, user_agent=user_agent,
        )
        return otp, code

    def verify(self, code):
        """Check a submitted code. Returns True on success and consumes it."""
        if self.status != OtpStatus.PENDING:
            return False
        if timezone.now() > self.expires_at:
            self.status = OtpStatus.EXPIRED
            self.save(update_fields=["status"])
            return False
        self.attempts += 1
        if self.attempts > self.max_attempts:
            self.status = OtpStatus.EXPIRED
            self.save(update_fields=["status", "attempts"])
            return False
        if self._hash(code) == self.code_hash:
            now = timezone.now()
            self.status = OtpStatus.CONSUMED
            self.verified_at = now
            self.consumed_at = now
            self.save(update_fields=["status", "verified_at", "consumed_at", "attempts"])
            return True
        self.save(update_fields=["attempts"])
        return False


# ==========================================================================
# Member ID sequence + code generator (ports member_id_sequences)
# ==========================================================================
import re as _re
from datetime import date as _date
from django.db import transaction as _txn


class MemberIdSequence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("org.Church", on_delete=models.CASCADE,
                               related_name="id_sequences", db_column="church_id")
    fellowship_code = models.TextField()
    year = models.IntegerField()
    last_seq = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "member_id_sequences"
        unique_together = ("church", "fellowship_code", "year")


def generate_member_code(church, fellowship_code="GEN"):
    """
    Produce the next member_code for a church using its member_id_template and
    the member_id_sequences counter (per church + fellowship_code + year).

    Template tokens supported (matches the default
    '{CHURCH_CODE}-{YEAR}-{SEQ:00000}'):
      {CHURCH_CODE}      -> church.short_code
      {FELLOWSHIP_CODE}  -> the passed fellowship_code
      {YEAR}             -> current year
      {SEQ}              -> next sequence, optional :0NNN zero-pad e.g. {SEQ:00000}
    """
    year = _date.today().year
    template = church.member_id_template or "{CHURCH_CODE}-{YEAR}-{SEQ:00000}"

    with _txn.atomic():
        seq_row, _ = (MemberIdSequence.objects
                      .select_for_update()
                      .get_or_create(church=church, fellowship_code=fellowship_code,
                                     year=year, defaults={"last_seq": 0}))
        seq_row.last_seq += 1
        seq_row.save(update_fields=["last_seq", "updated_at"])
        seq = seq_row.last_seq

    def _sub(m):
        token = m.group(1)
        if token == "CHURCH_CODE":
            return church.short_code or "CE"
        if token == "FELLOWSHIP_CODE":
            return fellowship_code
        if token == "YEAR":
            return str(year)
        if token.startswith("SEQ"):
            # {SEQ} or {SEQ:00000}
            if ":" in token:
                pad = token.split(":", 1)[1]
                width = len(pad)
                return str(seq).zfill(width)
            return str(seq)
        return m.group(0)

    return _re.sub(r"\{([^}]+)\}", _sub, template)
