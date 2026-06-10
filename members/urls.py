from django.urls import path
from . import views

urlpatterns = [
    path("members/", views.member_list, name="member_list"),
    path("members/new/", views.member_create, name="member_create"),
    path("members/<uuid:member_id>/", views.member_detail, name="member_detail"),
    path("members/<uuid:member_id>/edit/", views.member_edit, name="member_edit"),
    path("members/<uuid:member_id>/archive/", views.member_archive, name="member_archive"),
]
