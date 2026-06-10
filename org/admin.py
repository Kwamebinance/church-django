from django.contrib import admin
from .models import (
    EcclesiasticalUnit, Church, MinistryGroup, Department, Fellowship, Cell,
)

for m in (EcclesiasticalUnit, Church, MinistryGroup, Department, Fellowship, Cell):
    admin.site.register(m)
