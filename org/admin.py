from django.contrib import admin
from .models import (
    EcclesiasticalUnit, Church, MinistryGroup, Department, Fellowship, Cell,
    ChurchSettings,
)

for m in (EcclesiasticalUnit, Church, MinistryGroup, Department, Fellowship, Cell):
    admin.site.register(m)


@admin.register(ChurchSettings)
class ChurchSettingsAdmin(admin.ModelAdmin):
    list_display = ("church", "require_income_approval")
