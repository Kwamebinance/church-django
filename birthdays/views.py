"""
Birthday list — derived from members' date_of_birth. Year-agnostic: matches on
month + day so it works across year/month boundaries (e.g. a week spanning
Dec 31 -> Jan 1). Reach-scoped via the shared scope_filter.

No new tables for the list. The card generator (next slice) adds
BirthdayCardTemplate + Pillow composition; the per-row "Generate card" button is
shown here but disabled until then.
"""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from accounts.enums import AccessLevel
from accounts.models import Member
from accounts.permissions import can_access, scope_filter


def _require_leader(request):
    profile = getattr(request, "profile", None)
    if not can_access(profile, AccessLevel.UNIT_LEADER):
        raise PermissionDenied("You do not have access to birthdays.")
    return profile


def _md(d):
    """(month, day) tuple for year-agnostic comparison; Feb 29 -> treat as Feb 28."""
    if d.month == 2 and d.day == 29:
        return (2, 28)
    return (d.month, d.day)


def _days_until(birth, today):
    """Days until the next occurrence of this birthday (0 = today)."""
    bm, bd = _md(birth)
    year = today.year
    try:
        nxt = date(year, bm, bd)
    except ValueError:
        nxt = date(year, bm, 28)
    if nxt < today:
        try:
            nxt = date(year + 1, bm, bd)
        except ValueError:
            nxt = date(year + 1, bm, 28)
    return (nxt - today).days


@login_required
def birthday_list(request):
    profile = _require_leader(request)
    today = date.today()
    period = request.GET.get("period", "month")

    qs = scope_filter(Member.objects.select_related("church", "cell", "cell__fellowship"), profile)
    qs = qs.filter(is_active=True, archived_at__isnull=True, date_of_birth__isnull=False)

    if period == "today":
        window = 0
    elif period == "week":
        window = 7
    else:  # month
        window = 31

    people = []
    for m in qs:
        d = _days_until(m.date_of_birth, today)
        if d <= window:
            bm, bd = _md(m.date_of_birth)
            # age they'll turn on this upcoming birthday
            next_bday_year = today.year if d >= 0 and (bm, bd) >= _md(today) else today.year
            if d > 0 and (bm, bd) < _md(today):
                next_bday_year = today.year + 1
            turning = next_bday_year - m.date_of_birth.year
            people.append({
                "m": m, "days": d, "is_today": d == 0,
                "month": bm, "day": bd, "turning": turning,
            })
    people.sort(key=lambda p: p["days"])

    return render(request, "birthdays/list.html", {
        "people": people, "period": period, "today": today,
        "count": len(people),
    })


# ============================================================================
# Card generator: template management (admin+) + generation flow
# ============================================================================
import uuid as _uuid
from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from accounts.permissions import reach_church_ids
from .models import BirthdayCardTemplate
from .cards import compose_card


def _require_admin(request):
    profile = getattr(request, "profile", None)
    if not can_access(profile, AccessLevel.ADMIN):
        raise PermissionDenied("Managing birthday templates requires admin access.")
    return profile


def _scoped_templates(profile):
    qs = BirthdayCardTemplate.objects.select_related("church")
    reach = reach_church_ids(profile)
    if reach is None:
        return qs
    return qs.filter(church_id__in=reach)


def _save_upload(f):
    ext = (f.name.rsplit(".", 1)[-1] or "png").lower()[:5]
    name = f"birthday_templates/{_uuid.uuid4().hex}.{ext}"
    return default_storage.save(name, ContentFile(f.read()))


@login_required
def template_list(request):
    profile = _require_admin(request)
    templates = _scoped_templates(profile).order_by("-is_active", "name")
    return render(request, "birthdays/template_list.html", {"templates": templates})


@login_required
def template_form(request, template_id=None):
    profile = _require_admin(request)
    template = None
    if template_id:
        template = get_object_or_404(_scoped_templates(profile), id=template_id)
    from org.models import Church
    reach = reach_church_ids(profile)
    churches = (Church.objects.filter(status="active") if reach is None
                else Church.objects.filter(id__in=reach, status="active"))

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        church_id = request.POST.get("church_id")
        if not name or not church_id:
            messages.error(request, "Name and church are required.")
            return redirect("bd_template_list")
        if template is None:
            template = BirthdayCardTemplate(church_id=church_id)
            if profile and profile.member_id:
                template.created_by = profile.member_id
        template.name = name
        template.church_id = church_id
        template.is_active = bool(request.POST.get("is_active"))
        for fld in ("photo_x", "photo_y", "photo_size", "name_x", "name_y",
                    "name_size", "message_x", "message_y", "message_size"):
            val = request.POST.get(fld)
            if val not in (None, ""):
                try:
                    setattr(template, fld, int(val))
                except ValueError:
                    pass
        template.photo_circle = bool(request.POST.get("photo_circle"))
        template.text_color = (request.POST.get("text_color") or "#FFFFFF")[:9]
        from .cards import FONT_FAMILIES
        nf = request.POST.get("name_font")
        mf = request.POST.get("message_font")
        template.name_font = nf if nf in FONT_FAMILIES else "default"
        template.message_font = mf if mf in FONT_FAMILIES else "default"
        template.text_stroke = (request.POST.get("text_stroke") or "").strip()[:9] or None
        sw = request.POST.get("text_stroke_width")
        if sw not in (None, ""):
            try:
                template.text_stroke_width = int(sw)
            except ValueError:
                pass
        if request.FILES.get("background"):
            template.image_path = _save_upload(request.FILES["background"])
        template.save()
        messages.success(request, "Template saved.")
        return redirect("bd_template_list")

    from .cards import FONT_LABELS
    return render(request, "birthdays/template_form.html",
                  {"t": template, "churches": churches, "font_options": FONT_LABELS})


@login_required
def generate(request, member_id):
    profile = _require_leader(request)
    member = get_object_or_404(scope_filter(Member.objects.select_related("church"), profile),
                               id=member_id)
    templates = _scoped_templates(profile).filter(is_active=True)
    default_msg = f"Happy Birthday, {member.preferred_name or member.other_names}!"

    if request.method == "POST":
        template = get_object_or_404(templates, id=request.POST.get("template_id"))
        message = request.POST.get("message") or default_msg
        png = compose_card(template, member, message)
        resp = HttpResponse(png, content_type="image/png")
        fname = f"birthday_{member.member_code}.png"
        disp = "attachment" if request.POST.get("download") else "inline"
        resp["Content-Disposition"] = f'{disp}; filename="{fname}"'
        return resp

    return render(request, "birthdays/generate.html",
                  {"member": member, "templates": templates, "default_msg": default_msg,
                   "font_ok": _font_health_ok()})


def _font_health_ok():
    from .cards import font_health
    h = font_health()
    return h["bold_bundled"] and h["regular_bundled"]


@login_required
def diagnose_view(request):
    """Admin-only font/render diagnostic for the card generator."""
    _require_admin(request)
    from .cards import diagnose
    import json
    info = diagnose()
    body = "<h2>Birthday card diagnostics</h2><pre style='font-family:monospace;font-size:13px;background:#f4f4f8;padding:16px;border-radius:8px;white-space:pre-wrap;'>"
    body += json.dumps(info, indent=2, default=str)
    body += "</pre>"
    body += "<p>Send this output back so the text-rendering issue can be pinpointed.</p>"
    from django.http import HttpResponse
    return HttpResponse(body)
