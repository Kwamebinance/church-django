"""
Net-new models for the controlled self-registration onboarding flow. These do
NOT exist in the original Supabase schema; they are specific to this rebuild's
2-week self-registration window + cell-leader approval. Kept in their own app so
the ported tables stay faithful to the original schema.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class RegistrationWindow(models.Model):
    """
    Admin-controlled switch for whether public self-registration is open.
    Singleton-style: we use the single most-recent row (helper below).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_open = models.BooleanField(default=False)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "registration_window"

    @classmethod
    def current(cls):
        return cls.objects.order_by("-updated_at").first()

    @classmethod
    def is_registration_open(cls):
        w = cls.current()
        if w is None or not w.is_open:
            return False
        now = timezone.now()
        if w.opens_at and now < w.opens_at:
            return False
        if w.closes_at and now > w.closes_at:
            return False
        return True

    def __str__(self):
        return f"Registration {'OPEN' if self.is_open else 'CLOSED'}"


class RegistrationRequest(models.Model):
    """
    One self-registration awaiting cell-leader/admin approval. Links the created
    (pending) User + Member; carries the approval state and reviewer notes.
    """
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="registration_request",
    )
    member = models.ForeignKey(
        "accounts.Member", on_delete=models.CASCADE,
        related_name="registration_requests",
    )
    # Denormalised for fast queue filtering / display without extra joins.
    cell = models.ForeignKey("org.Cell", on_delete=models.SET_NULL, null=True, blank=True)
    church = models.ForeignKey("org.Church", on_delete=models.SET_NULL, null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_registrations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "registration_requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.member} -> {self.status}"
