from django.urls import path
from . import views

urlpatterns = [
    path("events/<uuid:event_id>/register/", views.register, name="attendance_register"),
    path("events/<uuid:event_id>/close/", views.close_register, name="attendance_close"),
    path("events/<uuid:event_id>/reopen/", views.reopen_register, name="attendance_reopen"),
    path("events/<uuid:event_id>/add-expected/", views.add_expected, name="attendance_add_expected"),
    path("events/<uuid:event_id>/add-expected/search/", views.add_expected_search, name="attendance_add_expected_search"),
    path("events/<uuid:event_id>/count/", views.add_count, name="attendance_add_count"),
    path("events/<uuid:event_id>/count/<uuid:count_id>/remove/", views.remove_count, name="attendance_remove_count"),
]
