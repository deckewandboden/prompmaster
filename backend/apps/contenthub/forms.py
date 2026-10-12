from django import forms
from django.utils.translation import gettext_lazy as _

from .models import FAQEntry


class FAQEntryForm(forms.ModelForm):
    class Meta:
        model = FAQEntry
        fields = ['key', 'question', 'answer', 'audience', 'sort_order', 'active']
        labels = {
            'key': _('Schlüssel'),
            'question': _('Frage'),
            'answer': _('Antwort'),
            'audience': _('Zielgruppe'),
            'sort_order': _('Sortierung'),
            'active': _('Aktiv'),
        }
        widgets = {'answer': forms.Textarea(attrs={'rows': 8})}
