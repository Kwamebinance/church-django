from django.urls import path
from . import views, template_views as tv

urlpatterns = [
    path("events/", views.event_list, name="event_list"),
    path("events/calendar/", views.event_calendar, name="event_calendar"),
    path("events/new/", views.event_create, name="event_create"),
    path("events/<uuid:event_id>/", views.event_detail, name="event_detail"),
    path("events/<uuid:event_id>/edit/", views.event_edit, name="event_edit"),
    path("events/<uuid:event_id>/cancel/", views.event_cancel, name="event_cancel"),

    # recurring templates
    path("templates/", tv.template_list, name="template_list"),
    path("templates/new/", tv.template_create, name="template_create"),
    path("templates/<uuid:template_id>/", tv.template_detail, name="template_detail"),
    path("templates/<uuid:template_id>/edit/", tv.template_edit, name="template_edit"),
    path("templates/<uuid:template_id>/generate/", tv.template_generate, name="template_generate"),
    path("templates/<uuid:template_id>/exception/", tv.template_add_exception, name="template_add_exception"),
    path("templates/<uuid:template_id>/exception/<uuid:exc_id>/remove/", tv.template_remove_exception, name="template_remove_exception"),
]
