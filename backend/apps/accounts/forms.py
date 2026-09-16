from django import forms
from django.contrib.auth import authenticate, password_validation


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        self.user = authenticate(
            email=(data.get('email') or '').strip().lower(),
            password=data.get('password'),
        )
        if not self.user or not self.user.is_active:
            raise forms.ValidationError('Anmeldung fehlgeschlagen.')
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
