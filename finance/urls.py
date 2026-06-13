from django.urls import path
from . import views

urlpatterns = [
    path("finance/", views.fin_home, name="fin_home"),
    path("finance/accounts/", views.account_list, name="fin_account_list"),
    path("finance/accounts/new/", views.account_form, name="fin_account_create"),
    path("finance/accounts/<uuid:account_id>/edit/", views.account_form, name="fin_account_edit"),
    path("finance/accounts/<uuid:account_id>/archive/", views.account_archive, name="fin_account_archive"),
    path("finance/accounts/<uuid:account_id>/categories/", views.category_list, name="fin_category_list"),
    path("finance/accounts/<uuid:account_id>/categories/new/", views.category_form, name="fin_category_create"),
    path("finance/accounts/<uuid:account_id>/categories/<uuid:category_id>/edit/", views.category_form, name="fin_category_edit"),
    path("finance/rates/", views.rate_list, name="fin_rate_list"),
    path("finance/rates/save/", views.rate_save, name="fin_rate_save"),
    path("finance/rates/<uuid:church_id>/history/", views.rate_history, name="fin_rate_history"),
    path("finance/settings/<uuid:church_id>/", views.settings_view, name="fin_settings"),
    path("finance/income/new/", views.income_create, name="fin_income_create"),
    path("finance/income/<uuid:record_id>/", views.income_detail, name="fin_income_detail"),
    path("finance/income/<uuid:record_id>/approve/", views.income_approve, name="fin_income_approve"),
    path("finance/income/<uuid:record_id>/reject/", views.income_reject, name="fin_income_reject"),
    path("finance/income/<uuid:record_id>/void/", views.income_void, name="fin_income_void"),
]
