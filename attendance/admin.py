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


from .models import AttendanceVisitor, FirstTimerContact


@admin.register(AttendanceVisitor)
class AttendanceVisitorAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "event", "stage", "visitor_type", "converted_to_member")
    list_filter = ("stage", "visitor_type", "is_first_time")
    search_fields = ("name", "phone")
    raw_id_fields = ("event", "invited_by_member", "follow_up_member", "converted_to_member")


@admin.register(FirstTimerContact)
class FirstTimerContactAdmin(admin.ModelAdmin):
    list_display = ("visitor", "contact_date", "method", "contacted_by_member")
    list_filter = ("method",)
    raw_id_fields = ("visitor",)
