from django import forms
from django.contrib.auth import authenticate, password_validation

from apps.audit.services import audit
from .models import User
from .security import clear_login_failures, login_lock_remaining, register_login_failure


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    def clean(self):
        data = super().clean()
        email = (data.get('email') or '').strip().lower()
        known_user = User.objects.filter(email__iexact=email).first() if email else None
        remaining = login_lock_remaining(email)
        if remaining:
            if known_user:
                audit(
                    known_user,
                    'auth.login_locked',
                    known_user,
                    {'remaining_seconds': remaining},
                    request=self.request,
                )
            raise forms.ValidationError('Anmeldung fehlgeschlagen. Bitte später erneut versuchen.')

        self.user = authenticate(email=email, password=data.get('password'))
        if not self.user or not self.user.is_active:
            failures, locked = register_login_failure(email)
            if known_user:
                audit(
                    known_user,
                    'auth.login_failed',
                    known_user,
                    {'failures': failures, 'locked': locked},
                    request=self.request,
                )
            raise forms.ValidationError('Anmeldung fehlgeschlagen.')

        clear_login_failures(email)
        return data


class OtpForm(forms.Form):
    code = forms.CharField(min_length=6, max_length=20)


class RegistrationForm(forms.Form):
    customer_type = forms.ChoiceField(choices=[('company', 'Unternehmen'), ('private', 'Privat')])
    first_name = forms.CharField(max_length=120)
    last_name = forms.CharField(max_length=120)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=12)
    company_name = forms.CharField(max_length=200, required=False)
    accept_terms = forms.BooleanField(label='AGB gelesen und akzeptiert')
    accept_privacy = forms.BooleanField(label='Datenschutzerklärung zur Kenntnis genommen')

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean(self):
        data = super().clean()
        password = data.get('password')
        if password:
            password_validation.validate_password(password)
        if data.get('customer_type') == 'company' and not data.get('company_name'):
            self.add_error('company_name', 'Firmenname erforderlich.')
        return data


class AcceptInvitationForm(forms.Form):
    first_name = forms.CharField(max_length=120)
    last_name = forms.CharField(max_length=120)
    password = forms.CharField(widget=forms.PasswordInput, min_length=12)
    accept_terms = forms.BooleanField(label='AGB gelesen und akzeptiert')
    accept_privacy = forms.BooleanField(label='Datenschutzerklärung zur Kenntnis genommen')

    def clean_password(self):
        password = self.cleaned_data['password']
        password_validation.validate_password(password)
        return password


class TransferAdminForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label='Passwort zur Bestätigung')
    confirm = forms.BooleanField(label='Administratorübertragung verbindlich bestätigen')


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class PasswordResetConfirmForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, min_length=12, label='Neues Passwort')
    password_repeat = forms.CharField(widget=forms.PasswordInput, min_length=12, label='Passwort wiederholen')

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password') != data.get('password_repeat'):
            self.add_error('password_repeat', 'Passwörter stimmen nicht überein.')
        if data.get('password'):
            password_validation.validate_password(data['password'])
        return data


class RecoveryCodesRegenerateForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label='Passwort zur Bestätigung')
