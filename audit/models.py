"""
Audit log — a generic, write-once record of meaningful actions across the
system. Faithful port of the original audit_log table. Entries are immutable:
there is no edit/delete path (enforced in save()). Populated via the explicit
log_audit() helper at sensitive operations, so each entry carries a human
context and the acting user's id + email (the email is stored so the trail
survives even if the user record is later removed).
"""
import uuid
from django.db import models


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.UUIDField(null=True, blank=True)       # acting user (profile/user id)
    actor_email = models.TextField(null=True, blank=True)    # captured for durability
    table_name = models.TextField()                          # affected table
    row_id = models.UUIDField()                              # affected row
    action = models.TextField()                              # create|update|end|transfer|merge|...
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    context = models.TextField(null=True, blank=True)        # human description
    church_id = models.UUIDField(null=True, blank=True)      # for reach-scoping
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["table_name", "row_id"]),
            models.Index(fields=["church_id"]),
        ]

    def save(self, *args, **kwargs):
        # write-once: an existing entry can never be modified
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("Audit log entries are immutable and cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit log entries cannot be deleted.")

    def __str__(self):
        return f"{self.action} {self.table_name}/{self.row_id} by {self.actor_email or '?'}"
