from django import forms


class EmailLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email",
                                       "placeholder": "you@example.com"})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )


class OtpRequestForm(forms.Form):
    phone = forms.CharField(
        label="Phone number",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "tel",
                                      "placeholder": "+233..."})
    )


class OtpVerifyForm(forms.Form):
    code = forms.CharField(
        label="6-digit code",
        max_length=6,
        widget=forms.TextInput(attrs={"autofocus": True, "inputmode": "numeric",
                                      "placeholder": "123456"})
    )
