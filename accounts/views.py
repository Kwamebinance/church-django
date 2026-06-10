"""
Authentication views (server-rendered).

  - Email/password login uses Django's standard authenticate()/login(); because
    USERNAME_FIELD is 'email', the default ModelBackend authenticates by email.
  - Phone/OTP login: request a code (dev mode prints it to the server console),
    then verify it and log the matching user in.
  - dashboard: a login-required landing page; members are bounced to the portal.
"""
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import EmailLoginForm, OtpRequestForm, OtpVerifyForm
from .models import PhoneOtp
from .enums import OtpPurpose

User = get_user_model()


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")


def login_email(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = EmailLoginForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["email"],   # USERNAME_FIELD == email
            password=form.cleaned_data["password"],
        )
        if user is not None:
            login(request, user)
            return redirect(request.GET.get("next") or "dashboard")
        error = "Invalid email or password."
    return render(request, "accounts/login_email.html", {"form": form, "error": error})


def logout_view(request):
    logout(request)
    return redirect("login_email")


def login_otp_request(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = OtpRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"].strip()
        otp, code = PhoneOtp.issue(
            phone, purpose=OtpPurpose.REGISTER,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )
        # DEV MODE: print the code to the server console instead of sending SMS.
        # When a real SMS provider is wired, send `code` to `phone` here.
        print("\n" + "=" * 48)
        print(f"  [DEV OTP]  phone={phone}  code={code}")
        print("=" * 48 + "\n")
        request.session["otp_id"] = str(otp.id)
        request.session["otp_phone"] = phone
        return redirect("login_otp_verify")
    return render(request, "accounts/login_otp_request.html", {"form": form})


def login_otp_verify(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    otp_id = request.session.get("otp_id")
    phone = request.session.get("otp_phone")
    if not otp_id or not phone:
        return redirect("login_otp_request")

    form = OtpVerifyForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        try:
            otp = PhoneOtp.objects.get(id=otp_id)
        except PhoneOtp.DoesNotExist:
            return redirect("login_otp_request")
        if otp.verify(form.cleaned_data["code"].strip()):
            user = User.objects.filter(phone=phone).first()
            if user is None:
                error = "No account is registered with this phone number."
            else:
                # No password backend involved; specify the model backend.
                login(request, user,
                      backend="django.contrib.auth.backends.ModelBackend")
                request.session.pop("otp_id", None)
                request.session.pop("otp_phone", None)
                return redirect("dashboard")
        else:
            error = "Incorrect or expired code."
    return render(request, "accounts/login_otp_verify.html",
                  {"form": form, "error": error, "phone": phone})


@login_required
def dashboard(request):
    profile = getattr(request, "profile", None)
    # Member->portal bounce (the blueprint rule). The portal is built later;
    # for now members simply see a notice rather than the admin dashboard.
    if profile is not None and profile.access_level == "member":
        return render(request, "accounts/member_notice.html", {})
    return render(request, "accounts/dashboard.html", {"profile": profile})
