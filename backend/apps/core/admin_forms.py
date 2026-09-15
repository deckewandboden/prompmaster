from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.accounts.models import Permission, Role, User
from apps.companies.forms import CompanyForm
from apps.catalog.models import Feature, Product, ProductEntitlement
from apps.legal.models import LegalDocument, RetentionPolicy
from apps.notifications.models import EmailTemplate


class SupportAdminTransferForm(forms.Form):
    identity_verified = forms.BooleanField(
        required=True,
        label='Identität und Berechtigung des Ansprechpartners wurden geprüft',
    )
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={'rows': 3}),
        label='Interne Notiz zur Prüfung (optional)',
    )


class AdminCompanyForm(CompanyForm):
    class Meta(CompanyForm.Meta):
        fields = CompanyForm.Meta.fields + ['status']


class ProductForm(forms.ModelForm):
    features = forms.ModelMultipleChoiceField(
        queryset=Feature.objects.none(), required=False, widget=forms.CheckboxSelectMultiple,
        label='Features / Entitlements',
    )

    class Meta:
        model = Product
        fields = [
            'code', 'name', 'description', 'active', 'visible', 'purchasable',
            'default_license_days', 'default_device_limit', 'reminder_1_days',
            'reminder_2_days', 'critical_warning_days',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['features'].queryset = Feature.objects.order_by('name')
        if self.instance and self.instance.pk:
            self.fields['features'].initial = Feature.objects.filter(
                productentitlement__product=self.instance,
                productentitlement__enabled=True,
            )

    def save(self, commit=True):
        product = super().save(commit=commit)
        if commit and 'features' in self.cleaned_data:
            selected = set(self.cleaned_data['features'].values_list('pk', flat=True))
            existing = {row.feature_id: row for row in ProductEntitlement.objects.filter(product=product)}
            for feature in self.cleaned_data['features']:
                row = existing.get(feature.pk)
                if row:
                    if not row.enabled:
                        row.enabled = True
                        row.save(update_fields=['enabled', 'updated_at'])
                else:
                    ProductEntitlement.objects.create(product=product, feature=feature, enabled=True)
            ProductEntitlement.objects.filter(product=product).exclude(feature_id__in=selected).update(enabled=False)
        return product

    def clean(self):
        data = super().clean()
        r1 = data.get('reminder_1_days')
        r2 = data.get('reminder_2_days')
        critical = data.get('critical_warning_days')
        if None not in (r1, r2) and r1 <= r2:
            self.add_error('reminder_1_days', 'Reminder 1 muss vor Reminder 2 liegen (größere Tageszahl).')
        if None not in (r2, critical) and r2 <= critical:
            self.add_error('reminder_2_days', 'Reminder 2 muss vor der kritischen Warnphase liegen.')
        return data


class FeatureForm(forms.ModelForm):
    class Meta:
        model = Feature
        fields = ['code', 'name']

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class PriceVersionForm(forms.Form):
    price_type = forms.ChoiceField(choices=[('new', 'Neukauf'), ('renewal', 'Verlängerung')])
    gross_amount = forms.DecimalField(min_value=Decimal('0.00'), decimal_places=2, max_digits=10, label='Bruttopreis')
    currency = forms.CharField(max_length=3, initial='EUR')
    valid_from = forms.DateTimeField(initial=timezone.now, label='Gültig ab')

    def clean_currency(self):
        return self.cleaned_data['currency'].strip().upper()


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ['subject', 'body_text', 'active']


class ServiceAccountForm(forms.Form):
    SCOPE_CHOICES = [
        ('ops.read', 'Operations lesen'),
        ('prompt.read', 'Prompts lesen'),
        ('prompt.draft', 'Prompt-Drafts erzeugen'),
        ('prompt.test', 'Prompt-Tests ausführen'),
    ]
    name = forms.CharField(max_length=120)
    scopes = forms.MultipleChoiceField(choices=SCOPE_CHOICES, initial=['ops.read'])
    expires_at = forms.DateTimeField(required=False, label='Ablauf optional')


class LegalDocumentForm(forms.ModelForm):
    class Meta:
        model = LegalDocument
        fields = ['doc_type', 'version', 'content', 'valid_from', 'active']


class RetentionPolicyForm(forms.ModelForm):
    class Meta:
        model = RetentionPolicy
        fields = ['data_class', 'retain_days', 'active']
        help_texts = {
            'data_class': 'Unterstützt: expired_invitations, email_messages, revoked_devices, resolved_system_alerts, resolved_task_failures, expired_sessions.',
            'retain_days': 'Löschung erst nach dieser Anzahl Tage. Rechtliche Aufbewahrungsfristen separat prüfen.',
        }

    ALLOWED_DATA_CLASSES = {
        'expired_invitations', 'email_messages', 'revoked_devices',
        'resolved_system_alerts', 'resolved_task_failures', 'expired_sessions',
    }

    def clean_data_class(self):
        value = self.cleaned_data['data_class'].strip()
        if value not in self.ALLOWED_DATA_CLASSES:
            raise forms.ValidationError('Für diese Datenklasse existiert kein freigegebener Lösch-Handler.')
        return value


class DeletionRejectForm(forms.Form):
    notes = forms.CharField(widget=forms.Textarea, max_length=5000, label='Begründung')


class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Role
        fields = ['name', 'active', 'permissions']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].queryset = Permission.objects.order_by('code')


class StaffUserCreateForm(forms.Form):
    email = forms.EmailField(label='E-Mail')
    first_name = forms.CharField(max_length=120, label='Vorname')
    last_name = forms.CharField(max_length=120, label='Nachname')
    role = forms.ModelChoiceField(queryset=Role.objects.none(), label='Rolle')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].queryset = Role.objects.filter(active=True).order_by('name')

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError('Diese E-Mail-Adresse ist bereits registriert.')
        return value


class StaffUserRoleForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none())
    role = forms.ModelChoiceField(queryset=Role.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(is_staff=True, is_active=True).order_by('email')
        self.fields['role'].queryset = Role.objects.filter(active=True).order_by('name')


class MollieConfigForm(forms.Form):
    profile_id = forms.CharField(max_length=120, required=False, label='Profile ID')
    api_key = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Leer lassen, um den bestehenden Schlüssel unverändert zu lassen.',
    )


class GeneralSettingsForm(forms.Form):
    support_email = forms.EmailField(label='Support-Empfänger')
    disk_warning = forms.IntegerField(min_value=1, max_value=99, initial=80)
    disk_critical = forms.IntegerField(min_value=2, max_value=100, initial=90)
    ram_warning = forms.IntegerField(min_value=1, max_value=99, initial=80)
    ram_critical = forms.IntegerField(min_value=2, max_value=100, initial=90)
    cpu_warning = forms.IntegerField(min_value=1, max_value=100, initial=80)
    backup_warning_hours = forms.IntegerField(min_value=1, max_value=720, initial=8)
    backup_critical_hours = forms.IntegerField(min_value=2, max_value=720, initial=24)
    restore_warning_days = forms.IntegerField(min_value=1, max_value=365, initial=35)

    def clean(self):
        data = super().clean()
        for warning, critical in [('disk_warning', 'disk_critical'), ('ram_warning', 'ram_critical'), ('backup_warning_hours', 'backup_critical_hours')]:
            if data.get(warning) is not None and data.get(critical) is not None and data[warning] >= data[critical]:
                self.add_error(critical, 'Der kritische Wert muss über dem Warnwert liegen.')
        return data

class RefundForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea, required=False, max_length=2000, label='Begründung optional')
    confirm = forms.BooleanField(label='Erstattung verbindlich über Mollie auslösen')


class IntegrationSecretForm(forms.Form):
    value = forms.CharField(widget=forms.PasswordInput(render_value=False), max_length=500)
