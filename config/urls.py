from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("", include("accounts.urls")),
    path("", include("registration.urls")),
    path("", include("members.urls")),
    path("", include("events.urls")),
    path("", include("attendance.urls")),
    path("", include("firsttimers.urls")),
    path("", include("birthdays.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
