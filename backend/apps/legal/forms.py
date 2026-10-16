from django import forms
from django.utils.translation import gettext_lazy as _


class WithdrawalDeclarationForm(forms.Form):
    name = forms.CharField(
        max_length=240,
        label=_('Vor- und Nachname'),
    )
    email = forms.EmailField(
        label=_('E-Mail-Adresse für die Eingangsbestätigung'),
    )
    contract_reference = forms.CharField(
        max_length=160,
        label=_('Bestellnummer'),
        help_text=_('Die Bestellnummer finden Sie in Ihrer Bestell- bzw. Zahlungsbestätigung.'),
    )


class CancellationDeclarationForm(forms.Form):
    CANCELLATION_KIND = (
        ('ordinary', _('Ordentliche Kündigung')),
        ('extraordinary', _('Außerordentliche Kündigung')),
    )

    cancellation_kind = forms.ChoiceField(
        choices=CANCELLATION_KIND,
        label=_('Art der Kündigung'),
    )
    name = forms.CharField(
        max_length=240,
        label=_('Vor- und Nachname'),
    )
    email = forms.EmailField(
        label=_('E-Mail-Adresse für die Kündigungsbestätigung'),
    )
    contract_reference = forms.CharField(
        max_length=160,
        label=_('Vertrag / Bestellung / Kundennummer'),
        help_text=_('Zum Beispiel Bestellnummer oder Kundennummer.'),
    )
    requested_end_date = forms.DateField(
        required=False,
        label=_('Gewünschter Beendigungszeitpunkt'),
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text=_('Leer lassen für den frühestmöglichen Zeitpunkt.'),
    )
    reason = forms.CharField(
        required=False,
        label=_('Kündigungsgrund'),
        widget=forms.Textarea(attrs={'rows': 4}),
    )

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get('cancellation_kind') == 'extraordinary'
            and not (cleaned.get('reason') or '').strip()
        ):
            self.add_error(
                'reason',
                _('Bei einer außerordentlichen Kündigung ist der Kündigungsgrund erforderlich.'),
            )
        return cleaned
