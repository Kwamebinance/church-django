from django import forms
from .models import AttendanceEvent, UnitType, EventStatus
from org.models import Church, Department, Fellowship, Cell


class EventForm(forms.ModelForm):
    class Meta:
        model = AttendanceEvent
        fields = [
            "title", "description",
            "unit_type", "church", "department", "fellowship", "cell",
            "event_date", "event_time", "duration_minutes", "location",
        ]
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "event_time": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        scope_churches = kwargs.pop("scope_churches", None)
        super().__init__(*args, **kwargs)
        self.fields["church"].queryset = (
            scope_churches if scope_churches is not None
            else Church.objects.filter(status="active")
        )
        self.fields["department"].queryset = Department.objects.filter(archived_at__isnull=True)
        self.fields["fellowship"].queryset = Fellowship.objects.filter(archived_at__isnull=True)
        self.fields["cell"].queryset = Cell.objects.filter(archived_at__isnull=True)
        for f in ("department", "fellowship", "cell"):
            self.fields[f].required = False
        self.fields["title"].required = True

    def clean(self):
        cleaned = super().clean()
        ut = cleaned.get("unit_type")
        church = cleaned.get("church")
        dept, fel, cell = cleaned.get("department"), cleaned.get("fellowship"), cleaned.get("cell")

        # The unit matching unit_type must be supplied and must belong to the church.
        if ut == UnitType.DEPARTMENT:
            if not dept:
                self.add_error("department", "Select the department for a department-level event.")
            elif church and dept.church_id != church.id:
                self.add_error("department", "Department does not belong to the selected church.")
        elif ut == UnitType.FELLOWSHIP:
            if not fel:
                self.add_error("fellowship", "Select the fellowship for a fellowship-level event.")
            elif church and fel.church_id != church.id:
                self.add_error("fellowship", "Fellowship does not belong to the selected church.")
        elif ut == UnitType.CELL:
            if not cell:
                self.add_error("cell", "Select the cell for a cell-level event.")
            elif church and cell.fellowship.church_id != church.id:
                self.add_error("cell", "Cell does not belong to the selected church.")

        # Clear narrower-unit fields that don't apply to the chosen unit_type,
        # so a church-wide event doesn't carry a stray cell_id.
        if ut == UnitType.CHURCH:
            cleaned["department"] = cleaned["fellowship"] = cleaned["cell"] = None
        elif ut == UnitType.DEPARTMENT:
            cleaned["fellowship"] = cleaned["cell"] = None
        elif ut == UnitType.FELLOWSHIP:
            cleaned["cell"] = None
        return cleaned


class EventFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search",
                        widget=forms.TextInput(attrs={"placeholder": "Title or location"}))
    unit_type = forms.ChoiceField(
        choices=[("", "All levels")] + list(UnitType.choices), required=False)
    status = forms.ChoiceField(
        choices=[("", "All statuses")] + list(EventStatus.choices), required=False)
