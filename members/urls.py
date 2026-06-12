from django.urls import path
from . import views

urlpatterns = [
    path("members/", views.member_list, name="member_list"),
    path("members/new/", views.member_create, name="member_create"),
    path("members/<uuid:member_id>/", views.member_detail, name="member_detail"),
    path("members/<uuid:member_id>/qr/", views.member_qr_print, name="member_qr_print"),
    path("members/<uuid:member_id>/assignment/add/", views.assignment_add, name="assignment_add"),
    path("members/<uuid:member_id>/assignment/<uuid:assignment_id>/change-role/", views.assignment_change_role, name="assignment_change_role"),
    path("members/<uuid:member_id>/assignment/<uuid:assignment_id>/end/", views.assignment_end, name="assignment_end"),
    path("members/<uuid:member_id>/change-placement/", views.change_placement, name="change_placement"),
    path("members/<uuid:member_id>/upload-photo/", views.upload_photo, name="upload_photo"),

    path("members/<uuid:member_id>/edit/", views.member_edit, name="member_edit"),
    path("members/<uuid:member_id>/archive/", views.member_archive, name="member_archive"),
]
