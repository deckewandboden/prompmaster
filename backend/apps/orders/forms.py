from django import forms


class PurchaseForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=500, initial=1, label='Anzahl Lizenzen')
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
