"""
Birthday card template. Faithful port of birthday_card_templates PLUS net-new
position config (the original schema had no coordinate columns; we add them so
a leader can place the photo + text on any background design). Net-new fields
flagged for the data-migration phase — existing templates get default positions.
"""
import uuid
from django.db import models


class BirthdayCardTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey("org.Church", on_delete=models.CASCADE,
                               related_name="birthday_templates", db_column="church_id")
    name = models.TextField()
    image_path = models.TextField(null=True, blank=True)   # background image (MEDIA path)
    is_active = models.BooleanField(default=True)
    zones = models.JSONField(default=list)                  # org scope (list of unit ids/codes)
    created_by = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- NET-NEW position config (beyond Supabase schema) ---
    # all values are pixels relative to the background's natural size.
    photo_x = models.IntegerField(default=40)
    photo_y = models.IntegerField(default=40)
    photo_size = models.IntegerField(default=300)           # square box side
    photo_circle = models.BooleanField(default=True)         # circular-mask the photo
    name_x = models.IntegerField(default=40)
    name_y = models.IntegerField(default=360)
    name_size = models.IntegerField(default=64)
    message_x = models.IntegerField(default=40)
    message_y = models.IntegerField(default=440)
    message_size = models.IntegerField(default=36)
    text_color = models.CharField(max_length=9, default="#FFFFFF")  # hex
    text_stroke = models.CharField(max_length=9, null=True, blank=True)  # outline; auto if blank
    text_stroke_width = models.IntegerField(default=3)
    name_font = models.CharField(max_length=20, default="default")
    message_font = models.CharField(max_length=20, default="default")

    class Meta:
        db_table = "birthday_card_templates"
        ordering = ["name"]

    def __str__(self):
        return self.name
