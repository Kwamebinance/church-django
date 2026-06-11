from django import forms
from .models import EventTemplate, RecurrenceException, UnitType, RecurrenceType, WeekPosition
from org.models import Church, Department, Fellowship, Cell

DOW_CHOICES = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
    (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
]


class TemplateForm(forms.ModelForm):
    recurrence_day_of_week = forms.TypedChoiceField(
        choices=[("", "—")] + DOW_CHOICES, coerce=int, required=False,
        label="Day of week",
    )

    class Meta:
        model = EventTemplate
        fields = [
            "title", "description",
            "unit_type", "church", "department", "fellowship", "cell",
            "recurrence_type", "recurrence_day_of_week",
            "recurrence_week_position", "recurrence_day_of_month",
            "event_time", "duration_minutes", "default_location",
            "active_from", "active_until",
        ]
        widgets = {
            "event_time": forms.TimeInput(attrs={"type": "time"}),
            "active_from": forms.DateInput(attrs={"type": "date"}),
            "active_until": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        scope_churches = kwargs.pop("scope_churches", None)
        super().__init__(*args, **kwargs)
        self.fields["church"].queryset = (
            scope_churches if scope_churches is not None
            else Church.objects.filter(status="active"))
        self.fields["department"].queryset = Department.objects.filter(archived_at__isnull=True)
        self.fields["fellowship"].queryset = Fellowship.objects.filter(archived_at__isnull=True)
        self.fields["cell"].queryset = Cell.objects.filter(archived_at__isnull=True)
        for f in ("department", "fellowship", "cell", "recurrence_week_position",
                  "recurrence_day_of_month", "active_until", "description", "default_location"):
            self.fields[f].required = False
        self.fields["title"].required = True

    def clean(self):
        cleaned = super().clean()
        ut = cleaned.get("unit_type")
        church = cleaned.get("church")
        dept, fel, cell = cleaned.get("department"), cleaned.get("fellowship"), cleaned.get("cell")
        # scope integrity (same rules as events)
        if ut == UnitType.DEPARTMENT:
            if not dept:
                self.add_error("department", "Select the department.")
            elif church and dept.church_id != church.id:
                self.add_error("department", "Department not in the selected church.")
        elif ut == UnitType.FELLOWSHIP:
            if not fel:
                self.add_error("fellowship", "Select the fellowship.")
            elif church and fel.church_id != church.id:
                self.add_error("fellowship", "Fellowship not in the selected church.")
        elif ut == UnitType.CELL:
            if not cell:
                self.add_error("cell", "Select the cell.")
            elif church and cell.fellowship.church_id != church.id:
                self.add_error("cell", "Cell not in the selected church.")
        if ut == UnitType.CHURCH:
            cleaned["department"] = cleaned["fellowship"] = cleaned["cell"] = None
        elif ut == UnitType.DEPARTMENT:
            cleaned["fellowship"] = cleaned["cell"] = None
        elif ut == UnitType.FELLOWSHIP:
            cleaned["cell"] = None

        # recurrence-pattern integrity
        rt = cleaned.get("recurrence_type")
        dow = cleaned.get("recurrence_day_of_week")
        wpos = cleaned.get("recurrence_week_position")
        dom = cleaned.get("recurrence_day_of_month")
        if rt == RecurrenceType.WEEKLY:
            if dow in (None, ""):
                self.add_error("recurrence_day_of_week", "Choose which day of the week.")
        elif rt == RecurrenceType.MONTHLY:
            has_dom = bool(dom)
            has_pos = bool(wpos) and dow not in (None, "")
            if not (has_dom or has_pos):
                self.add_error("recurrence_type",
                    "For monthly, give either a day-of-month (e.g. 15) OR a week "
                    "position + day of week (e.g. Third + Sunday).")
        return cleaned


class ExceptionForm(forms.Form):
    exception_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(required=False,
                             widget=forms.TextInput(attrs={"placeholder": "e.g. public holiday"}))
