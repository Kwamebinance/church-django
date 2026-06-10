"""
Registration + approval + password-reset (OTP) views.

Scope note: the approval queue uses accounts.reach_church_ids() to decide which
pending requests a reviewer sees. That helper is currently STUBBED
(super_admin = all; everyone else = their own church). So today the queue is
correctly scoped to church for admins and shows all for super_admin; the finer
"cell leader sees only their own cell" filter activates once the full scope
logic is built. The cell-level filter is already coded below behind that helper.
"""
import uuid
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone

from django.conf import settings
from accounts.models import Member, Profile, PhoneOtp, reach_church_ids, has_at_least
from accounts.enums import AccessLevel, OtpPurpose
from org.models import Fellowship, Cell
from .models import RegistrationWindow, RegistrationRequest
from .forms import (
    SelfRegisterForm, ResetRequestForm, ResetVerifyForm, ReviewForm,
)

User = get_user_model()


# ---- cascading dropdown JSON endpoints (minimal, no framework) -------------
def api_fellowships(request):
    church_id = request.GET.get("church")
    rows = (Fellowship.objects.filter(church_id=church_id, archived_at__isnull=True)
            .order_by("display_order", "name").values("id", "name")) if church_id else []
    return JsonResponse({"results": list(rows)})


def api_cells(request):
    fellowship_id = request.GET.get("fellowship")
    rows = (Cell.objects.filter(fellowship_id=fellowship_id, archived_at__isnull=True)
            .order_by("display_order", "name").values("id", "name")) if fellowship_id else []
    return JsonResponse({"results": list(rows)})


# ---- public self-registration ---------------------------------------------
def register(request):
    if not RegistrationWindow.is_registration_open():
        return render(request, "registration/closed.html", {})

    form = SelfRegisterForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data

        # Basic duplicate guard: same phone (or email) already on a member.
        dup = Member.objects.filter(phone_primary=cd["phone_primary"])
        if cd.get("email"):
            dup = dup | Member.objects.filter(email=cd["email"])
        if dup.exists():
            return render(request, "registration/register.html", {
                "form": form,
                "error": "A member with this phone or email already exists. "
                         "Please contact your cell leader instead of registering again.",
            })

        with transaction.atomic():
            # 1. the login account (member level, can log in -> holding page)
            user = User.objects.create_user(
                email=cd.get("email") or None,
                phone=cd["phone_primary"],
                password=cd["password"],
            )
            # 2. the pending member record
            member = Member.objects.create(
                church=cd["church"],
                member_code=_provisional_code(cd["church"]),
                surname=cd["surname"],
                other_names=cd["other_names"],
                gender=cd["gender"],
                date_of_birth=cd.get("date_of_birth"),
                marital_status=cd.get("marital_status") or None,
                phone_primary=cd["phone_primary"],
                email=cd.get("email") or None,
                cell=cd["cell"],
                is_active=False,            # pending until approved
                official_photo_path=_save_photo(request.FILES["photo"]),
            )
            # 3. the profile (member level) linking account -> member.
            #    The post_save signal already created a member-level Profile for
            #    this user; update it to attach the member + church.
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "member": member,
                    "access_level": AccessLevel.MEMBER,
                    "church": cd["church"],
                },
            )
            # 4. the approval request, routed by cell
            RegistrationRequest.objects.create(
                user=user, member=member, cell=cd["cell"], church=cd["church"],
            )
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("reg_pending")
    return render(request, "registration/register.html", {"form": form})


def _provisional_code(church):
    # Temporary code until an admin assigns the real member_code on approval.
    return f"PENDING-{uuid.uuid4().hex[:8].upper()}"


def _save_photo(f):
    """Store the uploaded photo under MEDIA_ROOT and return the relative path."""
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    ext = (f.name.rsplit(".", 1)[-1] or "jpg").lower()[:5]
    name = f"member_photos/{uuid.uuid4().hex}.{ext}"
    return default_storage.save(name, ContentFile(f.read()))


@login_required
def reg_pending(request):
    """Holding page for a member whose registration is awaiting approval."""
    req = RegistrationRequest.objects.filter(user=request.user).first()
    if req and req.status == RegistrationRequest.STATUS_APPROVED:
        return redirect("dashboard")
    return render(request, "registration/pending.html", {"req": req})


# ---- approval queue (cell leader / admin) ----------------------------------
@login_required
def approval_queue(request):
    profile = getattr(request, "profile", None)
    if not has_at_least(profile, AccessLevel.UNIT_LEADER):
        raise Http404()
    qs = RegistrationRequest.objects.filter(status=RegistrationRequest.STATUS_PENDING)
    reach = reach_church_ids(profile)
    if reach is not None:                       # None = super_admin (all)
        qs = qs.filter(church_id__in=reach)
    # NOTE: once full scope exists, unit_leaders are further narrowed to their
    # own cells here (e.g. qs.filter(cell_id__in=led_cell_ids)).
    qs = qs.select_related("member", "cell", "church")
    return render(request, "registration/queue.html", {"requests": qs})


@login_required
def review(request, req_id):
    profile = getattr(request, "profile", None)
    if not has_at_least(profile, AccessLevel.UNIT_LEADER):
        raise Http404()
    req = get_object_or_404(RegistrationRequest, id=req_id)
    reach = reach_church_ids(profile)
    if reach is not None and req.church_id not in reach:
        raise Http404()

    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            req.reviewed_by = request.user
            req.reviewed_at = timezone.now()
            req.review_notes = form.cleaned_data.get("notes") or ""
            if form.cleaned_data["decision"] == "approve":
                req.status = RegistrationRequest.STATUS_APPROVED
                m = req.member
                m.is_active = True            # now a real, active member
                # Replace the provisional PENDING- code with a real one, generated
                # from the church template + the cell's fellowship code.
                if (m.member_code or "").startswith("PENDING-"):
                    from accounts.models import generate_member_code
                    fellowship_code = (m.cell.fellowship.short_code
                                       if m.cell and m.cell.fellowship else "GEN")
                    m.member_code = generate_member_code(m.church, fellowship_code)
                    m.save(update_fields=["is_active", "member_code"])
                else:
                    m.save(update_fields=["is_active"])
            else:
                req.status = RegistrationRequest.STATUS_REJECTED
                # Rejected: deactivate the login so they can't proceed.
                u = req.user
                u.is_active = False
                u.save(update_fields=["is_active"])
            req.save()
        return redirect("reg_queue")
    return render(request, "registration/review.html", {"req": req, "form": form})


# ---- password reset via phone OTP ------------------------------------------
def reset_request(request):
    form = ResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"].strip()
        otp, code = PhoneOtp.issue(phone, purpose=OtpPurpose.REGISTER)
        print("\n" + "=" * 48)
        print(f"  [DEV PASSWORD-RESET OTP]  phone={phone}  code={code}")
        print("=" * 48 + "\n")
        request.session["reset_otp_id"] = str(otp.id)
        request.session["reset_phone"] = phone
        return redirect("reset_verify")
    return render(request, "registration/reset_request.html", {"form": form})


def reset_verify(request):
    otp_id = request.session.get("reset_otp_id")
    phone = request.session.get("reset_phone")
    if not otp_id or not phone:
        return redirect("reset_request")
    form = ResetVerifyForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        try:
            otp = PhoneOtp.objects.get(id=otp_id)
        except PhoneOtp.DoesNotExist:
            return redirect("reset_request")
        if otp.verify(form.cleaned_data["code"].strip()):
            user = User.objects.filter(phone=phone).first()
            if user is None:
                error = "No account is registered with this phone number."
            else:
                user.set_password(form.cleaned_data["new_password"])
                user.save(update_fields=["password"])
                request.session.pop("reset_otp_id", None)
                request.session.pop("reset_phone", None)
                return render(request, "registration/reset_done.html", {})
        else:
            error = "Incorrect or expired code."
    return render(request, "registration/reset_verify.html",
                  {"form": form, "error": error, "phone": phone})
