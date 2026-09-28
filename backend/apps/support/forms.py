from django import forms

from .models import SupportRequest, SupportMessage


class SupportReplyForm(forms.Form):
    visibility = forms.ChoiceField(
        choices=SupportMessage.VISIBILITY,
        initial='customer',
        label='Nachrichtentyp',
    )
    body = forms.CharField(
        max_length=5000,
        label='Nachricht',
        widget=forms.Textarea(
            attrs={
                'rows': 8,
                'placeholder': 'Antwort an den Kunden oder interne Notiz eingeben …',
            }
        ),
    )
    status_after_message = forms.ChoiceField(
        required=False,
        label='Status nach dem Speichern',
        choices=[('', 'Status beibehalten')] + SupportRequest.STATUS,
    )

    def clean_body(self):
        body = (self.cleaned_data.get('body') or '').strip()
        if not body:
            raise forms.ValidationError('Bitte geben Sie eine Nachricht ein.')
        return body
