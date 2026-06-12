from django import forms
from accounts.models import Member
from accounts.enums import Gender, MaritalStatus, BaptismStatus, FoundationSchoolStatus
from org.models import Church, Fellowship, Cell, Department, EcclesiasticalUnit


class MemberForm(forms.ModelForm):
    """Create / edit a member. Bound to real Member columns.

    member_code is NOT a form field on create -- it's auto-generated server-side
    via accounts.generate_member_code. On edit it's shown read-only in the view.
    Placement uses church + cell (fellowship is implied by the cell); the
    cascading UI narrows choices, the server validates integrity.
    """
    class Meta:
        model = Member
        fields = [
            "title", "surname", "other_names", "preferred_name",
            "academic_title", "maiden_name",
            "gender", "date_of_birth", "marital_status",
            "phone_primary", "phone_whatsapp", "telegram_username", "email",
            "address", "city", "country",
            "occupation", "employer",
            "baptism_status", "born_again_date",
            "foundation_school_status", "foundation_school_completion_date",
            "date_joined",
            "church", "cell",
            "is_active", "inactive_reason",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "born_again_date": forms.DateInput(attrs={"type": "date"}),
            "foundation_school_completion_date": forms.DateInput(attrs={"type": "date"}),
            "date_joined": forms.DateInput(attrs={"type": "date"}),
            "inactive_reason": forms.Textarea(attrs={"rows": 2}),
        }

    # Optional photo upload (stored to MEDIA, path saved on the member).
    photo = forms.ImageField(required=False, label="Photo (optional)")

    def __init__(self, *args, **kwargs):
        # `scope_churches` limits which churches are selectable to the user's reach.
        scope_churches = kwargs.pop("scope_churches", None)
        super().__init__(*args, **kwargs)
        self.fields["church"].queryset = (
            scope_churches if scope_churches is not None
            else Church.objects.filter(status="active")
        )
        self.fields["cell"].queryset = Cell.objects.filter(archived_at__isnull=True)
        self.fields["cell"].required = False
        # Friendly required set
        for f in ("surname", "other_names"):
            self.fields[f].required = True

    def clean(self):
        cleaned = super().clean()
        church, cell = cleaned.get("church"), cleaned.get("cell")
        if cell and church and cell.fellowship.church_id != church.id:
            self.add_error("cell", "Cell does not belong to the selected church.")
        return cleaned


class MemberFilterForm(forms.Form):
    """The list search + filter bar (zone→group→church→fellowship→cell + dept)."""
    q = forms.CharField(required=False, label="Search",
                        widget=forms.TextInput(attrs={"placeholder": "Search name or member code"}))
    zone = forms.ModelChoiceField(queryset=EcclesiasticalUnit.objects.none(), required=False, empty_label="Any zone")
    group = forms.ModelChoiceField(queryset=EcclesiasticalUnit.objects.none(), required=False, empty_label="Any group")
    church = forms.ModelChoiceField(queryset=Church.objects.none(), required=False, empty_label="Any church")
    fellowship = forms.ModelChoiceField(queryset=Fellowship.objects.none(), required=False, empty_label="Any fellowship")
    cell = forms.ModelChoiceField(queryset=Cell.objects.none(), required=False, empty_label="Any cell")
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False, empty_label="Any department")
    gender = forms.ChoiceField(choices=[("", "Any gender")] + list(Gender.choices), required=False)
    marital_status = forms.ChoiceField(
        choices=[("", "Any marital status")] + list(MaritalStatus.choices), required=False)
    baptism_status = forms.ChoiceField(
        choices=[("", "Any baptism status")] + list(BaptismStatus.choices), required=False)
    foundation_school_status = forms.ChoiceField(
        choices=[("", "Any FS status")] + list(FoundationSchoolStatus.choices), required=False)
    status = forms.ChoiceField(
        choices=[("", "Active + inactive"), ("active", "Active only"), ("inactive", "Inactive only")],
        required=False)

    def __init__(self, *args, **kwargs):
        scope_churches = kwargs.pop("scope_churches", None)
        super().__init__(*args, **kwargs)
        # Location dropdowns scoped to the user's reach where applicable.
        churches = (scope_churches if scope_churches is not None
                    else Church.objects.filter(status="active"))
        church_ids = list(churches.values_list("id", flat=True)) if hasattr(churches, "values_list") else None
        self.fields["church"].queryset = churches.order_by("name") if hasattr(churches, "order_by") else Church.objects.filter(status="active").order_by("name")
        self.fields["zone"].queryset = EcclesiasticalUnit.objects.filter(unit_type="zone", archived_at__isnull=True).order_by("name")
        self.fields["group"].queryset = EcclesiasticalUnit.objects.filter(unit_type="group", archived_at__isnull=True).order_by("name")
        fel_qs = Fellowship.objects.filter(archived_at__isnull=True)
        cell_qs = Cell.objects.filter(archived_at__isnull=True)
        dept_qs = Department.objects.filter(archived_at__isnull=True)
        if church_ids is not None:
            fel_qs = fel_qs.filter(church_id__in=church_ids)
            cell_qs = cell_qs.filter(fellowship__church_id__in=church_ids)
            dept_qs = dept_qs.filter(church_id__in=church_ids)
        self.fields["fellowship"].queryset = fel_qs.order_by("name")
        self.fields["cell"].queryset = cell_qs.order_by("name")
        self.fields["department"].queryset = dept_qs.order_by("name")
