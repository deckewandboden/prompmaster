from django import forms

from .models import FAQEntry


class FAQEntryForm(forms.ModelForm):
    class Meta:
        model = FAQEntry
        fields = ['key', 'question', 'answer', 'audience', 'sort_order', 'active']
        labels = {
            'key': 'Schlüssel',
            'question': 'Frage',
            'answer': 'Antwort',
            'audience': 'Zielgruppe',
            'sort_order': 'Sortierung',
            'active': 'Aktiv',
        }
        widgets = {'answer': forms.Textarea(attrs={'rows': 8})}
