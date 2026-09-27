from django import forms

from .services import MAX_PURCHASE_QUANTITY


class PurchaseForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=MAX_PURCHASE_QUANTITY, initial=1, label='Anzahl Lizenzen')
    accept_terms = forms.BooleanField(label='AGB akzeptieren')
    accept_privacy = forms.BooleanField(label='Datenschutzhinweise zur Kenntnis genommen')
    accept_withdrawal = forms.BooleanField(
        required=False,
        label='Widerrufsinformation zur Kenntnis genommen',
    )

    def __init__(self, *args, require_withdrawal=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_withdrawal = require_withdrawal
        self.fields['accept_withdrawal'].required = require_withdrawal
        if not require_withdrawal:
            self.fields.pop('accept_withdrawal')


class RenewalForm(forms.Form):
    accept_terms = forms.BooleanField(label='AGB akzeptieren')
    accept_privacy = forms.BooleanField(label='Datenschutzhinweise zur Kenntnis genommen')
    accept_withdrawal = forms.BooleanField(
        required=False,
        label='Widerrufsinformation zur Kenntnis genommen',
    )

    def __init__(self, *args, require_withdrawal=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accept_withdrawal'].required = require_withdrawal
        if not require_withdrawal:
            self.fields.pop('accept_withdrawal')

class PublicCheckoutForm(forms.Form):
    CUSTOMER_TYPES = (
        ('company', 'Unternehmen'),
        ('private', 'Privatkunde'),
    )

    quantity = forms.IntegerField(
        min_value=1,
        max_value=MAX_PURCHASE_QUANTITY,
        initial=1,
    )
    customer_type = forms.ChoiceField(choices=CUSTOMER_TYPES)
    first_name = forms.CharField(max_length=120)
    last_name = forms.CharField(max_length=120)
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(max_length=60, required=False)
    company_name = forms.CharField(max_length=200, required=False)
    legal_form = forms.CharField(max_length=80, required=False)
    vat_id = forms.CharField(max_length=40, required=False)
    tax_number = forms.CharField(max_length=60, required=False)
    street = forms.CharField(max_length=160)
    house_number = forms.CharField(max_length=40, required=False)
    postal_code = forms.CharField(max_length=20)
    city = forms.CharField(max_length=120)
    country = forms.ChoiceField(choices=(('DE', 'Deutschland'),))
    accept_terms = forms.BooleanField()
    accept_privacy = forms.BooleanField()
    accept_withdrawal = forms.BooleanField(required=False)

    def clean(self):
        cleaned = super().clean()
        customer_type = cleaned.get('customer_type')
        if customer_type == 'company':
            if not cleaned.get('company_name'):
                self.add_error('company_name', 'Unternehmensname ist erforderlich.')
        elif customer_type == 'private':
            if not cleaned.get('accept_withdrawal'):
                self.add_error(
                    'accept_withdrawal',
                    'Bitte bestätigen Sie die Widerrufsbelehrung.',
                )
        return cleaned

