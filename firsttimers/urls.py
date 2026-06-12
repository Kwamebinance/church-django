from django.urls import path
from . import views

urlpatterns = [
    path("first-timers/", views.queue, name="ft_queue"),
    path("first-timers/<uuid:visitor_id>/", views.detail, name="ft_detail"),
    path("first-timers/<uuid:visitor_id>/member-search/", views.member_search, name="ft_member_search"),
    path("first-timers/<uuid:visitor_id>/advance/", views.advance_stage, name="ft_advance"),
    path("first-timers/<uuid:visitor_id>/assign/", views.assign, name="ft_assign"),
    path("first-timers/<uuid:visitor_id>/contact/", views.log_contact, name="ft_log_contact"),
    path("first-timers/<uuid:visitor_id>/convert/", views.convert, name="ft_convert"),
]
