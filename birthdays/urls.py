from django.urls import path
from . import views

urlpatterns = [
    path("birthdays/", views.birthday_list, name="birthday_list"),
    path("birthdays/templates/", views.template_list, name="bd_template_list"),
    path("birthdays/templates/new/", views.template_form, name="bd_template_create"),
    path("birthdays/templates/<uuid:template_id>/edit/", views.template_form, name="bd_template_edit"),
    path("birthdays/<uuid:member_id>/generate/", views.generate, name="bd_generate"),
    path("birthdays/diagnose/", views.diagnose_view, name="bd_diagnose"),
]
