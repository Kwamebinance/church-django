from django import forms
from accounts.enums import Gender, MaritalStatus
from org.models import Church, Fellowship, Cell


class SelfRegisterForm(forms.Form):
    # Identity
    surname = forms.CharField(max_length=120)
    other_names = forms.CharField(max_length=120)
    gender = forms.ChoiceField(choices=Gender.choices)
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    marital_status = forms.ChoiceField(choices=MaritalStatus.choices, required=False)

    # Contact
    phone_primary = forms.CharField(max_length=40, label="Phone number")
    email = forms.EmailField(required=False)

    # Placement (cascading). Querysets for fellowship/cell are narrowed in __init__
    # based on submitted data so validation accepts the chosen values.
    church = forms.ModelChoiceField(queryset=Church.objects.none())
    fellowship = forms.ModelChoiceField(queryset=Fellowship.objects.none())
    cell = forms.ModelChoiceField(queryset=Cell.objects.none())

    # Required self-portrait
    photo = forms.ImageField(label="Your photo (clear, front-facing)")

    # Account
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active churches are selectable.
        self.fields["church"].queryset = Church.objects.filter(status="active")
        # Accept any active fellowship/cell at validation time; the cascading UI
        # narrows what the user sees, but the server must accept the posted ids.
        self.fields["fellowship"].queryset = Fellowship.objects.filter(archived_at__isnull=True)
        self.fields["cell"].queryset = Cell.objects.filter(archived_at__isnull=True)

    def clean(self):
        cleaned = super().clean()
        pw, pw2 = cleaned.get("password"), cleaned.get("password_confirm")
        if pw and pw2 and pw != pw2:
            self.add_error("password_confirm", "Passwords do not match.")

        # Integrity: chosen cell must belong to chosen fellowship, which must
        # belong to chosen church. Prevents mismatched cascading submissions.
        church, fellowship, cell = cleaned.get("church"), cleaned.get("fellowship"), cleaned.get("cell")
        if fellowship and church and fellowship.church_id != church.id:
            self.add_error("fellowship", "Fellowship does not belong to the selected church.")
        if cell and fellowship and cell.fellowship_id != fellowship.id:
            self.add_error("cell", "Cell does not belong to the selected fellowship.")
        return cleaned


class ResetRequestForm(forms.Form):
    phone = forms.CharField(label="Your phone number", max_length=40)


class ResetVerifyForm(forms.Form):
    code = forms.CharField(label="6-digit code", max_length=6)
    new_password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    new_password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm new password")

    def clean(self):
        cleaned = super().clean()
        a, b = cleaned.get("new_password"), cleaned.get("new_password_confirm")
        if a and b and a != b:
            self.add_error("new_password_confirm", "Passwords do not match.")
        return cleaned


class ReviewForm(forms.Form):
    """Cell-leader/admin approval action."""
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False,
                            help_text="Required when rejecting (reason shown to the registrant).")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") == "reject" and not (cleaned.get("notes") or "").strip():
            self.add_error("notes", "Please give a reason for rejecting.")
        return cleaned
