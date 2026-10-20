from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import TaxRule
from .services import MAX_PURCHASE_QUANTITY


class PurchaseForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=MAX_PURCHASE_QUANTITY, initial=1, label=_('Anzahl Lizenzen'))
    accept_terms = forms.BooleanField(label=_('AGB akzeptieren'))
    accept_privacy = forms.BooleanField(label=_('Datenschutzhinweise zur Kenntnis genommen'))
    accept_license = forms.BooleanField(label=_('Lizenzbedingungen akzeptieren'))
    accept_withdrawal = forms.BooleanField(
        required=False,
        label=_('Widerrufsinformation zur Kenntnis genommen'),
    )
    request_early_performance = forms.BooleanField(
        required=False,
        label=_('Leistungsbeginn vor Ablauf der Widerrufsfrist ausdrücklich verlangt'),
    )

    def __init__(self, *args, require_withdrawal=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_withdrawal = require_withdrawal
        self.fields['accept_withdrawal'].required = require_withdrawal
        self.fields['request_early_performance'].required = require_withdrawal
        if not require_withdrawal:
            self.fields.pop('accept_withdrawal')
            self.fields.pop('request_early_performance')


class RenewalForm(forms.Form):
    accept_terms = forms.BooleanField(label=_('AGB akzeptieren'))
    accept_privacy = forms.BooleanField(label=_('Datenschutzhinweise zur Kenntnis genommen'))
    accept_license = forms.BooleanField(label=_('Lizenzbedingungen akzeptieren'))
    accept_withdrawal = forms.BooleanField(
        required=False,
        label=_('Widerrufsinformation zur Kenntnis genommen'),
    )
    request_early_performance = forms.BooleanField(
        required=False,
        label=_('Leistungsbeginn vor Ablauf der Widerrufsfrist ausdrücklich verlangt'),
    )

    def __init__(self, *args, require_withdrawal=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accept_withdrawal'].required = require_withdrawal
        self.fields['request_early_performance'].required = require_withdrawal
        if not require_withdrawal:
            self.fields.pop('accept_withdrawal')
            self.fields.pop('request_early_performance')

class PublicCheckoutForm(forms.Form):
    CUSTOMER_TYPES = (
        ('company', _('Unternehmen')),
        ('private', _('Privatkunde')),
    )

    quantity = forms.IntegerField(
        min_value=1,
        max_value=MAX_PURCHASE_QUANTITY,
        initial=1,
        label=_('Anzahl Lizenzen'),
    )
    customer_type = forms.ChoiceField(choices=CUSTOMER_TYPES, label=_('Kundentyp'))
    first_name = forms.CharField(max_length=120, label=_('Vorname'))
    last_name = forms.CharField(max_length=120, label=_('Nachname'))
    email = forms.EmailField(max_length=254, label=_('E-Mail-Adresse'))
    phone = forms.CharField(max_length=60, required=False, label=_('Telefon'))
    company_name = forms.CharField(max_length=200, required=False, label=_('Firmenname'))
    legal_form = forms.CharField(max_length=80, required=False, label=_('Rechtsform'))
    vat_id = forms.CharField(max_length=40, required=False, label=_('USt-IdNr.'))
    tax_number = forms.CharField(max_length=60, required=False, label=_('Steuernummer'))
    street = forms.CharField(max_length=160, label=_('Straße'))
    house_number = forms.CharField(max_length=40, required=False, label=_('Hausnummer'))
    postal_code = forms.CharField(max_length=20, label=_('PLZ'))
    city = forms.CharField(max_length=120, label=_('Ort'))
    country = forms.ChoiceField(choices=(('DE', _('Deutschland')),), label=_('Land'))
    accept_terms = forms.BooleanField(label=_('AGB akzeptieren'))
    accept_privacy = forms.BooleanField(label=_('Datenschutzhinweise zur Kenntnis genommen'))
    accept_license = forms.BooleanField(label=_('Lizenzbedingungen akzeptieren'))
    accept_withdrawal = forms.BooleanField(required=False, label=_('Widerrufsinformation zur Kenntnis genommen'))
    request_early_performance = forms.BooleanField(required=False, label=_('Leistungsbeginn vor Ablauf der Widerrufsfrist ausdrücklich verlangt'))

    def clean(self):
        cleaned = super().clean()
        customer_type = cleaned.get('customer_type')
        if customer_type == 'company':
            if not cleaned.get('company_name'):
                self.add_error('company_name', _('Unternehmensname ist erforderlich.'))
            country = (cleaned.get('country') or '').upper()
            rule = TaxRule.objects.filter(
                country=country,
                customer_type='company',
                active=True,
            ).first()
            if rule:
                if rule.require_vat_id and not cleaned.get('vat_id'):
                    self.add_error(
                        'vat_id',
                        _('USt-IdNr. ist für diese Steuerregel erforderlich.'),
                    )
                if rule.require_tax_number and not cleaned.get('tax_number'):
                    self.add_error(
                        'tax_number',
                        _('Steuernummer ist für diese Steuerregel erforderlich.'),
                    )
        elif customer_type == 'private':
            if not cleaned.get('accept_withdrawal'):
                self.add_error(
                    'accept_withdrawal',
                    _('Bitte bestätigen Sie die Widerrufsbelehrung.'),
                )
            if not cleaned.get('request_early_performance'):
                self.add_error(
                    'request_early_performance',
                    _('Bitte bestätigen Sie den gewünschten Leistungsbeginn vor Ablauf der Widerrufsfrist.'),
                )
        return cleaned

