from django import forms

from apps.catalog.models import TaxRule
from apps.licenses.models import License
from .models import Company, PrivateCustomerProfile


class InviteForm(forms.Form):
    first_name = forms.CharField(max_length=120, label='Vorname')
    last_name = forms.CharField(max_length=120, label='Nachname')
    email = forms.EmailField(label='E-Mail-Adresse')

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            'name',
            'legal_form',
            'email',
            'phone',
            'street',
            'house_number',
            'postal_code',
            'city',
            'country',
            'vat_id',
            'tax_number',
        ]
        labels = {
            'name': 'Firmenname',
            'legal_form': 'Rechtsform',
            'email': 'E-Mail-Adresse',
            'phone': 'Telefon',
            'street': 'Straße',
            'house_number': 'Hausnummer',
            'postal_code': 'PLZ',
            'city': 'Ort',
            'country': 'Land',
            'vat_id': 'USt-IdNr.',
            'tax_number': 'Steuernummer',
        }

    def clean(self):
        data = super().clean()
        country = (data.get('country') or '').upper()
        rule = TaxRule.objects.filter(country=country, customer_type='company', active=True).first()
        if rule:
            if rule.require_vat_id and not data.get('vat_id'):
                self.add_error('vat_id', 'USt-IdNr. ist für diese Steuerregel erforderlich.')
            if rule.require_tax_number and not data.get('tax_number'):
                self.add_error('tax_number', 'Steuernummer ist für diese Steuerregel erforderlich.')
        return data


class PrivateCustomerForm(forms.ModelForm):
    class Meta:
        model = PrivateCustomerProfile
        fields = ['street', 'house_number', 'postal_code', 'city', 'country']
        labels = {
            'street': 'Straße',
            'house_number': 'Hausnummer',
            'postal_code': 'PLZ',
            'city': 'Ort',
            'country': 'Land',
        }


class SupportForm(forms.Form):
    category = forms.ChoiceField(
        choices=[
            ('license', 'Lizenz'),
            ('payment', 'Zahlung'),
            ('user', 'Benutzer'),
            ('device', 'Gerät'),
            ('technical', 'Technisches Problem'),
            ('privacy', 'Datenschutz'),
            ('other', 'Sonstiges'),
        ]
    )
    license = forms.ModelChoiceField(
        queryset=License.objects.none(),
        required=False,
        label='Lizenz (optional)',
        empty_label='Keine konkrete Lizenz',
    )
    subject = forms.CharField(max_length=180, label='Betreff')
    message = forms.CharField(widget=forms.Textarea, max_length=5000, label='Nachricht')

    def __init__(self, *args, license_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['license'].queryset = (
            license_queryset if license_queryset is not None else License.objects.none()
        )


class UserProfileForm(forms.Form):
    first_name = forms.CharField(max_length=120, label='Vorname')
    last_name = forms.CharField(max_length=120, label='Nachname')
