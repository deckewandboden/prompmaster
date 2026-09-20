from __future__ import annotations

import json

from django import forms
from django.core.exceptions import ValidationError

from .models import PromptTestCase, PromptVersion


def _lines(value):
    return [line.strip() for line in str(value or '').splitlines() if line.strip()]


class PromptVersionEditorForm(forms.ModelForm):
    required_fields = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 6}),
        label='Pflichtfelder',
        help_text='Ein Pflichtfeld pro Zeile.',
    )
    optional_fields = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 6}),
        label='Optionale Felder',
        help_text='Ein Feld pro Zeile. Optionales Fragment: Feldname ||| Text mit {value}.',
    )
    sources = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 5}), label='Quellen')
    outputs = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 5}), label='Ausgabeformen')
    focuses = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 5}), label='Schwerpunkte')
    audiences = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 5}), label='Zielgruppen')

    class Meta:
        model = PromptVersion
        fields = ['title', 'area', 'family', 'intent', 'max_chars', 'context_template', 'app_rule_snapshot']
        labels = {
            'title': 'Titel',
            'area': 'Bereich',
            'family': 'Familie',
            'intent': 'Ziel / Intent',
            'max_chars': 'Maximale Zeichen',
            'context_template': 'Kontextvorlage',
            'app_rule_snapshot': 'App-Regel-Snapshot',
        }
        widgets = {
            'intent': forms.Textarea(attrs={'rows': 7}),
            'context_template': forms.Textarea(attrs={'rows': 5}),
            'app_rule_snapshot': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            required = self.instance.fields.filter(kind='required').order_by('sort_order')
            optional = self.instance.fields.filter(kind='optional').order_by('sort_order')
            self.fields['required_fields'].initial = '\n'.join(field.label for field in required)
            self.fields['optional_fields'].initial = '\n'.join(
                f'{field.label} ||| {field.optional_fragment}' if field.optional_fragment else field.label
                for field in optional
            )
            for kind, form_field in [('source', 'sources'), ('output', 'outputs'), ('focus', 'focuses'), ('audience', 'audiences')]:
                self.fields[form_field].initial = '\n'.join(
                    option.value for option in self.instance.options.filter(kind=kind).order_by('sort_order')
                )

    def clean(self):
        cleaned = super().clean()
        if self.instance and self.instance.lifecycle != 'DRAFT':
            raise ValidationError('Nur DRAFT-Versionen dürfen inhaltlich bearbeitet werden.')
        required = _lines(cleaned.get('required_fields'))
        optional_rows = _lines(cleaned.get('optional_fields'))
        labels = required + [row.split('|||', 1)[0].strip() for row in optional_rows]
        if len(labels) != len(set(labels)):
            raise ValidationError('Feldbezeichnungen müssen innerhalb einer Prompt-Version eindeutig sein.')
        return cleaned

    def save_related_prompt_structure(self, version):
        from .models import PromptField, PromptOption

        version.fields.all().delete()
        for index, label in enumerate(_lines(self.cleaned_data.get('required_fields'))):
            PromptField.objects.create(version=version, label=label, kind='required', sort_order=index)
        for index, row in enumerate(_lines(self.cleaned_data.get('optional_fields'))):
            if '|||' in row:
                label, fragment = [part.strip() for part in row.split('|||', 1)]
            else:
                label, fragment = row, ''
            PromptField.objects.create(
                version=version,
                label=label,
                kind='optional',
                sort_order=index,
                optional_fragment=fragment,
            )

        version.options.all().delete()
        groups = [
            ('source', 'sources'), ('output', 'outputs'), ('focus', 'focuses'), ('audience', 'audiences')
        ]
        for kind, form_field in groups:
            for index, value in enumerate(_lines(self.cleaned_data.get(form_field))):
                PromptOption.objects.create(
                    version=version,
                    kind=kind,
                    value=value,
                    label=value,
                    sort_order=index,
                )


class PromptTestCaseForm(forms.ModelForm):
    input_payload_text = forms.CharField(
        label='Test-Payload (JSON)',
        widget=forms.Textarea(attrs={'rows': 12}),
        help_text='Beispiel: {"microsoft_tier":"premium","payload":{"fields":{...}}}',
    )
    expected_contains_text = forms.CharField(required=False, label='Muss enthalten', widget=forms.Textarea(attrs={'rows': 5}))
    expected_not_contains_text = forms.CharField(required=False, label='Darf nicht enthalten', widget=forms.Textarea(attrs={'rows': 5}))

    class Meta:
        model = PromptTestCase
        fields = ['name', 'enabled', 'sort_order']
        labels = {'name': 'Name', 'enabled': 'Aktiv', 'sort_order': 'Sortierung'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['input_payload_text'].initial = json.dumps(self.instance.input_payload, ensure_ascii=False, indent=2)
            self.fields['expected_contains_text'].initial = '\n'.join(self.instance.expected_contains or [])
            self.fields['expected_not_contains_text'].initial = '\n'.join(self.instance.expected_not_contains or [])
        else:
            self.fields['input_payload_text'].initial = json.dumps(
                {
                    'microsoft_tier': 'premium',
                    'payload': {
                        'fields': {},
                        'tone': 'professional',
                        'detail': 'standard',
                    },
                },
                ensure_ascii=False,
                indent=2,
            )

    def clean_input_payload_text(self):
        raw = self.cleaned_data['input_payload_text']
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f'Ungültiges JSON: {exc}') from exc
        if not isinstance(payload, dict):
            raise ValidationError('Test-Payload muss ein JSON-Objekt sein.')
        return payload

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.input_payload = self.cleaned_data['input_payload_text']
        obj.expected_contains = _lines(self.cleaned_data.get('expected_contains_text'))
        obj.expected_not_contains = _lines(self.cleaned_data.get('expected_not_contains_text'))
        if commit:
            obj.save()
        return obj


class PromptPreviewForm(forms.Form):
    microsoft_tier = forms.ChoiceField(
        label='Microsoft-Lizenzstufe',
        choices=[('chatbasic', 'Copilot Chat'), ('m365basic', 'M365 Copilot (Basic)'), ('premium', 'Microsoft 365 Copilot Business')]
    )
    payload_json = forms.CharField(label='Eingabedaten (JSON)', widget=forms.Textarea(attrs={'rows': 18}))

    def clean_payload_json(self):
        try:
            value = json.loads(self.cleaned_data['payload_json'])
        except json.JSONDecodeError as exc:
            raise ValidationError(f'Ungültiges JSON: {exc}') from exc
        if not isinstance(value, dict):
            raise ValidationError('Payload muss ein JSON-Objekt sein.')
        return value


class PromptQualityPolicyForm(forms.ModelForm):
    class Meta:
        from .models import PromptQualityPolicy
        model = PromptQualityPolicy
        fields = [
            'name', 'minimum_average', 'critical_average', 'warning_drop', 'critical_drop',
            'recent_sample_size', 'previous_sample_size', 'minimum_samples',
        ]
        labels = {
            'name': 'Name',
            'minimum_average': 'Mindestdurchschnitt',
            'critical_average': 'Kritischer Durchschnitt',
            'warning_drop': 'Warnung bei Abfall',
            'critical_drop': 'Kritisch bei Abfall',
            'recent_sample_size': 'Aktuelle Stichprobengröße',
            'previous_sample_size': 'Vorherige Stichprobengröße',
            'minimum_samples': 'Mindestanzahl Stichproben',
        }
