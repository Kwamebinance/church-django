from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_email, name="login_email"),
    path("logout/", views.logout_view, name="logout"),
    path("login/phone/", views.login_otp_request, name="login_otp_request"),
    path("login/phone/verify/", views.login_otp_verify, name="login_otp_verify"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
