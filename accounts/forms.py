from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm as DjangoAuthForm
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class SignupForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_password(self):
        pw = self.cleaned_data["password"]
        validate_password(pw)
        return pw

    def save(self) -> User:
        return User.objects.create_user(
            email=self.cleaned_data["email"], password=self.cleaned_data["password"]
        )


class EmailAuthenticationForm(DjangoAuthForm):
    """Login by email. Django's AuthenticationForm calls the field `username` —
    we just relabel it."""

    username = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}), label="Email")
