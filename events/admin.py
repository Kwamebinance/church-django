from django.contrib import admin
from .models import AttendanceEvent, EventTemplate, RecurrenceException


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(admin.ModelAdmin):
    list_display = ("display_title", "event_date", "event_time", "unit_type", "church", "status", "template")
    list_filter = ("unit_type", "status")
    search_fields = ("title", "location")
    date_hierarchy = "event_date"


@admin.register(EventTemplate)
class EventTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "recurrence_type", "unit_type", "church", "event_time", "active_from", "active_until")
    list_filter = ("recurrence_type", "unit_type")
    search_fields = ("title",)


@admin.register(RecurrenceException)
class RecurrenceExceptionAdmin(admin.ModelAdmin):
    list_display = ("template", "exception_date", "reason")
