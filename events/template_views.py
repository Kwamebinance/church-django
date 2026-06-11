"""
Recurring templates: list, detail, create, edit, generate-forward, add/remove
exceptions. Same counter+ access and reach-scoping as events; generated events
inherit the template's scope.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from accounts.enums import AccessLevel
from accounts.permissions import can_access, scope_filter
from .models import EventTemplate, RecurrenceException, AttendanceEvent
from .template_forms import TemplateForm, ExceptionForm
from .views import _require_counter, _scoped_churches


@login_required
def template_list(request):
    profile = _require_counter(request)
    qs = scope_filter(
        EventTemplate.objects.select_related("church", "cell", "fellowship", "department")
        .filter(archived_at__isnull=True), profile)
    return render(request, "events/template_list.html", {"templates": qs})


@login_required
def template_detail(request, template_id):
    profile = _require_counter(request)
    qs = scope_filter(EventTemplate.objects.all(), profile)
    tpl = get_object_or_404(qs, id=template_id)
    upcoming = (AttendanceEvent.objects.filter(template=tpl, event_date__gte=date.today())
                .order_by("event_date")[:20])
    exceptions = tpl.exceptions.order_by("exception_date")
    return render(request, "events/template_detail.html", {
        "t": tpl, "upcoming": upcoming, "exceptions": exceptions,
        "exc_form": ExceptionForm(),
    })


@login_required
def template_create(request):
    profile = _require_counter(request)
    form = TemplateForm(request.POST or None, scope_churches=_scoped_churches(profile))
    if request.method == "POST" and form.is_valid():
        tpl = form.save(commit=False)
        tpl.created_by = request.user
        tpl.save()
        return redirect("template_detail", template_id=tpl.id)
    return render(request, "events/template_form.html", {"form": form, "mode": "create"})


@login_required
def template_edit(request, template_id):
    profile = _require_counter(request)
    qs = scope_filter(EventTemplate.objects.all(), profile)
    tpl = get_object_or_404(qs, id=template_id)
    form = TemplateForm(request.POST or None, instance=tpl,
                        scope_churches=_scoped_churches(profile))
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("template_detail", template_id=tpl.id)
    return render(request, "events/template_form.html", {"form": form, "mode": "edit", "t": tpl})


@login_required
def template_generate(request, template_id):
    profile = _require_counter(request)
    qs = scope_filter(EventTemplate.objects.all(), profile)
    tpl = get_object_or_404(qs, id=template_id)
    if request.method == "POST":
        try:
            weeks = int(request.POST.get("weeks", 8))
        except (TypeError, ValueError):
            weeks = 8
        weeks = max(1, min(weeks, 52))
        n = tpl.generate_forward(weeks=weeks, created_by=request.user)
        messages.success(request, f"Generated {n} new event(s) over the next {weeks} weeks.")
    return redirect("template_detail", template_id=tpl.id)


@login_required
def template_add_exception(request, template_id):
    profile = _require_counter(request)
    qs = scope_filter(EventTemplate.objects.all(), profile)
    tpl = get_object_or_404(qs, id=template_id)
    if request.method == "POST":
        form = ExceptionForm(request.POST)
        if form.is_valid():
            RecurrenceException.objects.get_or_create(
                template=tpl, exception_date=form.cleaned_data["exception_date"],
                defaults={"reason": form.cleaned_data.get("reason") or None,
                          "cancelled_by": request.user})
    return redirect("template_detail", template_id=tpl.id)


@login_required
def template_remove_exception(request, template_id, exc_id):
    profile = _require_counter(request)
    qs = scope_filter(EventTemplate.objects.all(), profile)
    tpl = get_object_or_404(qs, id=template_id)
    if request.method == "POST":
        RecurrenceException.objects.filter(id=exc_id, template=tpl).delete()
    return redirect("template_detail", template_id=tpl.id)
