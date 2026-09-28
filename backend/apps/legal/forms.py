from django import forms


class WithdrawalDeclarationForm(forms.Form):
    name = forms.CharField(
        max_length=240,
        label='Vor- und Nachname',
    )
    email = forms.EmailField(
        label='E-Mail-Adresse für die Eingangsbestätigung',
    )
    contract_reference = forms.CharField(
        max_length=160,
        label='Bestellnummer',
        help_text='Die Bestellnummer finden Sie in Ihrer Bestell- bzw. Zahlungsbestätigung.',
    )


class CancellationDeclarationForm(forms.Form):
    CANCELLATION_KIND = (
        ('ordinary', 'Ordentliche Kündigung'),
        ('extraordinary', 'Außerordentliche Kündigung'),
    )

    cancellation_kind = forms.ChoiceField(
        choices=CANCELLATION_KIND,
        label='Art der Kündigung',
    )
    name = forms.CharField(
        max_length=240,
        label='Vor- und Nachname',
    )
    email = forms.EmailField(
        label='E-Mail-Adresse für die Kündigungsbestätigung',
    )
    contract_reference = forms.CharField(
        max_length=160,
        label='Vertrag / Bestellung / Kundennummer',
        help_text='Zum Beispiel Bestellnummer oder Kundennummer.',
    )
    requested_end_date = forms.DateField(
        required=False,
        label='Gewünschter Beendigungszeitpunkt',
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Leer lassen für den frühestmöglichen Zeitpunkt.',
    )
    reason = forms.CharField(
        required=False,
        label='Kündigungsgrund',
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
                'Bei einer außerordentlichen Kündigung ist der Kündigungsgrund erforderlich.',
            )
        return cleaned
