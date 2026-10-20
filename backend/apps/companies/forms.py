from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import TaxRule
from apps.licenses.models import License
from .models import Company, PrivateCustomerProfile


class InviteForm(forms.Form):
    first_name = forms.CharField(max_length=120, label=_('Vorname'))
    last_name = forms.CharField(max_length=120, label=_('Nachname'))
    email = forms.EmailField(label=_('E-Mail-Adresse'))

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
            'name': _('Firmenname'),
            'legal_form': _('Rechtsform'),
            'email': _('E-Mail-Adresse'),
            'phone': _('Telefon'),
            'street': _('Straße'),
            'house_number': _('Hausnummer'),
            'postal_code': _('PLZ'),
            'city': _('Ort'),
            'country': _('Land'),
            'vat_id': _('USt-IdNr.'),
            'tax_number': _('Steuernummer'),
        }

    def clean(self):
        data = super().clean()
        country = (data.get('country') or '').upper()
        rule = TaxRule.objects.filter(country=country, customer_type='company', active=True).first()
        if rule:
            if rule.require_vat_id and not data.get('vat_id'):
                self.add_error('vat_id', _('USt-IdNr. ist für diese Steuerregel erforderlich.'))
            if rule.require_tax_number and not data.get('tax_number'):
                self.add_error('tax_number', _('Steuernummer ist für diese Steuerregel erforderlich.'))
        return data


class PrivateCustomerForm(forms.ModelForm):
    class Meta:
        model = PrivateCustomerProfile
        fields = ['phone', 'street', 'house_number', 'postal_code', 'city', 'country']
        labels = {
            'phone': _('Telefon'),
            'street': _('Straße'),
            'house_number': _('Hausnummer'),
            'postal_code': _('PLZ'),
            'city': _('Ort'),
            'country': _('Land'),
        }


class SupportForm(forms.Form):
    category = forms.ChoiceField(
        choices=[
            ('license', _('Lizenz')),
            ('payment', _('Zahlung')),
            ('user', _('Benutzer')),
            ('device', _('Gerät')),
            ('technical', _('Technisches Problem')),
            ('privacy', _('Datenschutz')),
            ('other', _('Sonstiges')),
        ]
    )
    license = forms.ModelChoiceField(
        queryset=License.objects.none(),
        required=False,
        label=_('Lizenz (optional)'),
        empty_label=_('Keine konkrete Lizenz'),
    )
    subject = forms.CharField(max_length=180, label=_('Betreff'))
    message = forms.CharField(widget=forms.Textarea, max_length=5000, label=_('Nachricht'))

    def __init__(self, *args, license_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['license'].queryset = (
            license_queryset if license_queryset is not None else License.objects.none()
        )


class UserProfileForm(forms.Form):
    first_name = forms.CharField(max_length=120, label=_('Vorname'))
    last_name = forms.CharField(max_length=120, label=_('Nachname'))
