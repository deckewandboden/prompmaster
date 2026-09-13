from django import forms

from .models import FAQEntry


class FAQEntryForm(forms.ModelForm):
    class Meta:
        model = FAQEntry
        fields = ['key', 'question', 'answer', 'audience', 'sort_order', 'active']
        widgets = {'answer': forms.Textarea(attrs={'rows': 8})}
