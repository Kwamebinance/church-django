from django.contrib import admin
from .models import AttendanceRecord, CountContribution, EventExpectedAttendee


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("event", "member", "presence", "recorded_by", "created_at")
    list_filter = ("presence",)
    raw_id_fields = ("event", "member")


@admin.register(CountContribution)
class CountContributionAdmin(admin.ModelAdmin):
    list_display = ("event", "label", "count", "counted_by", "created_at")
    raw_id_fields = ("event",)


@admin.register(EventExpectedAttendee)
class EventExpectedAttendeeAdmin(admin.ModelAdmin):
    list_display = ("event", "member", "is_added", "created_at")
    list_filter = ("is_added",)
    raw_id_fields = ("event", "member")
