from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.accounts.models import Permission, Role, User
from apps.companies.forms import CompanyForm
from apps.companies.models import Company
from apps.core.models import Lead
from apps.catalog.models import Feature, Product, ProductEntitlement
from apps.legal.models import LegalDocument, RetentionPolicy
from apps.notifications.models import EmailTemplate


class LeadForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label='Zuständig',
        empty_label='Nicht zugewiesen',
    )

    class Meta:
        model = Lead
        fields = [
            'kind', 'company_name', 'first_name', 'last_name', 'email', 'phone',
            'source', 'status', 'priority', 'assigned_to', 'next_action_at', 'notes',
        ]
        labels = {
            'kind': 'Lead-Typ',
            'company_name': 'Unternehmen',
            'first_name': 'Vorname',
            'last_name': 'Nachname',
            'email': 'E-Mail',
            'phone': 'Telefon',
            'source': 'Quelle',
            'status': 'Status',
            'priority': 'Priorität',
            'next_action_at': 'Nächste Aktion',
            'notes': 'Interne Notizen',
        }
        widgets = {
            'next_action_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by('last_name', 'first_name', 'email')

    def clean(self):
        data = super().clean()
        if data.get('kind') == 'company' and not (data.get('company_name') or '').strip():
            self.add_error('company_name', 'Für Unternehmens-Leads ist der Unternehmensname erforderlich.')
        return data


    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        duplicates = Lead.objects.filter(
            email__iexact=value,
            deleted_at__isnull=True,
        )
        if self.instance and self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError(
                'Für diese E-Mail-Adresse existiert bereits ein aktiver Lead.'
            )
        return value


class LeadAssignForm(forms.Form):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label='Zuständig',
        empty_label='Nicht zugewiesen',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by('last_name', 'first_name', 'email')


class LeadDeleteForm(forms.Form):
    confirm = forms.BooleanField(
        label='Lead wirklich löschen',
        help_text='Der Datensatz wird revisionssicher ausgeblendet und im Audit protokolliert.',
    )


class LeadConvertCompanyForm(forms.Form):
    company_name = forms.CharField(max_length=200, label='Unternehmensname')
    legal_form = forms.CharField(max_length=80, required=False, label='Rechtsform')
    email = forms.EmailField(label='E-Mail des Firmenadministrators')
    first_name = forms.CharField(max_length=120, label='Vorname')
    last_name = forms.CharField(max_length=120, label='Nachname')
    phone = forms.CharField(max_length=60, required=False, label='Telefon')
    street = forms.CharField(max_length=160, required=False, label='Straße')
    house_number = forms.CharField(max_length=40, required=False, label='Hausnummer')
    postal_code = forms.CharField(max_length=20, required=False, label='PLZ')
    city = forms.CharField(max_length=120, required=False, label='Ort')
    country = forms.CharField(max_length=2, initial='DE', label='Land')
    vat_id = forms.CharField(max_length=40, required=False, label='USt-IdNr.')
    tax_number = forms.CharField(max_length=60, required=False, label='Steuernummer')
    confirm = forms.BooleanField(
        label='Lead in Firmenkunden umwandeln und Einladungslink senden',
    )


    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(
                'Diese E-Mail-Adresse gehört bereits zu einem PromptMaster-Konto.'
            )
        if Company.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(
                'Diese E-Mail-Adresse ist bereits einem Firmenkunden zugeordnet.'
            )
        return value


class CustomerAdminInviteForm(forms.Form):
    email = forms.EmailField(label='E-Mail des Firmenadministrators')
    first_name = forms.CharField(max_length=120, label='Vorname')
    last_name = forms.CharField(max_length=120, label='Nachname')

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(
                'Diese E-Mail-Adresse gehört bereits zu einem PromptMaster-Konto.'
            )
        return value


class SupportAdminTransferForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        label='Eigenes Passwort erneut eingeben',
        help_text='Sicherheitsbestätigung des aktuell angemeldeten netstyle Benutzers.',
    )
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
        labels = {
            'code': 'Produktcode',
            'name': 'Name',
            'description': 'Beschreibung',
            'active': 'Aktiv',
            'visible': 'Sichtbar',
            'purchasable': 'Kaufbar',
            'default_license_days': 'Standard-Laufzeit in Tagen',
            'default_device_limit': 'Geräte je Benutzer',
            'reminder_1_days': 'Erinnerung 1 · Tage vorher',
            'reminder_2_days': 'Erinnerung 2 · Tage vorher',
            'critical_warning_days': 'Kritische Warnung · Tage vorher',
        }

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
        labels = {'code': 'Code', 'name': 'Name'}

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class PriceVersionForm(forms.Form):
    price_type = forms.ChoiceField(label='Preistyp', choices=[('new', 'Neukauf'), ('renewal', 'Verlängerung')])
    gross_amount = forms.DecimalField(min_value=Decimal('0.00'), decimal_places=2, max_digits=10, label='Bruttopreis')
    currency = forms.CharField(max_length=3, initial='EUR', label='Währung')
    valid_from = forms.DateTimeField(initial=timezone.now, label='Gültig ab')

    def clean_currency(self):
        return self.cleaned_data['currency'].strip().upper()


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ['subject', 'body_text', 'active']
        labels = {'subject': 'Betreff', 'body_text': 'Nachrichtentext', 'active': 'Aktiv'}


class ServiceAccountForm(forms.Form):
    SCOPE_CHOICES = [
        ('ops.read', 'Operations lesen'),
        ('prompt.read', 'Prompts lesen'),
        ('prompt.draft', 'Prompt-Drafts erzeugen'),
        ('prompt.test', 'Prompt-Tests ausführen'),
    ]
    name = forms.CharField(max_length=120, label='Name')
    scopes = forms.MultipleChoiceField(label='Berechtigungen', choices=SCOPE_CHOICES, initial=['ops.read'])
    expires_at = forms.DateTimeField(required=False, label='Ablauf optional')


class LegalDocumentForm(forms.ModelForm):
    class Meta:
        model = LegalDocument
        fields = ['doc_type', 'version', 'content', 'valid_from', 'active']
        labels = {
            'doc_type': 'Dokumenttyp',
            'version': 'Version',
            'content': 'Inhalt',
            'valid_from': 'Gültig ab',
            'active': 'Aktiv',
        }


class RetentionPolicyForm(forms.ModelForm):
    class Meta:
        model = RetentionPolicy
        fields = ['data_class', 'retain_days', 'active']
        labels = {'data_class': 'Datenklasse', 'retain_days': 'Aufbewahrung in Tagen', 'active': 'Aktiv'}
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


PERMISSION_DOMAIN_LABELS = {
    'customers': 'Kunden',
    'leads': 'Leads',
    'licenses': 'Lizenzen',
    'devices': 'Geräte',
    'orders': 'Bestellungen',
    'payments': 'Zahlungen',
    'products': 'Produkte & Preise',
    'email': 'E-Mail',
    'ops': 'System & Betrieb',
    'api': 'API & Integrationen',
    'roles': 'Benutzer & Rollen',
    'legal': 'Datenschutz & Recht',
    'support': 'Kontaktanfragen',
    'audit': 'Protokolle',
    'settings': 'Einstellungen',
    'prompts': 'Prompt Studio',
    'content': 'FAQ & Inhalte',
}
PERMISSION_ACTION_LABELS = {
    'read': 'Lesen',
    'assign': 'Zuweisen',
    'convert': 'In Kunde umwandeln',
    'delete': 'Löschen',
    'write': 'Bearbeiten',
    'refund': 'Erstatten',
    'compose': 'Prompts erzeugen',
    'publish': 'Veröffentlichen',
    'quality': 'Qualität verwalten',
}


class PermissionChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        if obj.name and obj.name != obj.code:
            return f'{obj.name} ({obj.code})'
        domain, _, action = obj.code.partition('.')
        domain_label = PERMISSION_DOMAIN_LABELS.get(domain, domain.replace('_', ' ').title())
        action_label = PERMISSION_ACTION_LABELS.get(action, action.replace('_', ' ').title())
        return f'{domain_label}: {action_label} ({obj.code})'


class RoleForm(forms.ModelForm):
    permissions = PermissionChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Berechtigungen',
    )

    class Meta:
        model = Role
        fields = ['name', 'active', 'permissions']
        labels = {'name': 'Rollenname', 'active': 'Aktiv'}

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
    user = forms.ModelChoiceField(queryset=User.objects.none(), label='Benutzer')
    role = forms.ModelChoiceField(queryset=Role.objects.none(), label='Rolle')

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
        label='API-Schlüssel',
        help_text='Leer lassen, um den bestehenden Schlüssel unverändert zu lassen.',
    )


class GeneralSettingsForm(forms.Form):
    MAIL_PROVIDER_CHOICES = [
        ('smtp1', 'SMTP 1'),
        ('smtp2', 'SMTP 2'),
        ('graph', 'Microsoft 365 / Entra ID (Microsoft Graph)'),
    ]
    MAIL_FALLBACK_CHOICES = [
        ('', 'Kein weiterer Fallback'),
        *MAIL_PROVIDER_CHOICES,
    ]
    MAIL_DELIVERY_MODE_CHOICES = [
        ('manual', 'Manuell – nur den primären Versandweg verwenden'),
        ('failover', 'Automatisch – bei sicherem Ausfall auf Fallback wechseln'),
    ]

    support_email = forms.EmailField(label='Support-Empfänger')
    ops_alert_recipients = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        label='Monitoring-Alarmempfänger',
        help_text='Eine oder mehrere E-Mail-Adressen, getrennt durch Zeilenumbruch, Komma oder Semikolon.',
    )
    mail_delivery_mode = forms.ChoiceField(
        choices=MAIL_DELIVERY_MODE_CHOICES,
        required=False,
        label='Versandmodus',
        help_text='Im automatischen Modus wird nur bei eindeutig nicht zugestellten Fehlern weitergeschaltet.',
    )
    mail_provider = forms.ChoiceField(
        choices=MAIL_PROVIDER_CHOICES,
        required=False,
        label='Primärer Versandweg',
        help_text='SMTP 1, SMTP 2 und Microsoft Graph bleiben parallel konfiguriert.',
    )
    mail_fallback_1 = forms.ChoiceField(
        choices=MAIL_FALLBACK_CHOICES,
        required=False,
        label='Fallback 1',
    )
    mail_fallback_2 = forms.ChoiceField(
        choices=MAIL_FALLBACK_CHOICES,
        required=False,
        label='Fallback 2',
    )
    mail_from_email = forms.EmailField(
        required=False,
        label='Absender-E-Mail',
        help_text='Aktive Absenderadresse für SMTP. Änderungen gelten ohne Container-Neustart.',
    )
    mail_from_name = forms.CharField(
        max_length=120,
        required=False,
        label='Absender-Anzeigename',
        help_text='Zum Beispiel PromptMaster.',
    )
    mail_reply_to = forms.EmailField(
        required=False,
        label='Antwortadresse',
        help_text='Optional. Leer lassen, wenn Antworten an die Absenderadresse gehen sollen.',
    )
    mail_domain = forms.CharField(
        max_length=253,
        required=False,
        label='Mail-Domain',
        help_text='Domain des sichtbaren Absenders, z. B. decke-wand-boden.de oder später promptmaster.ai.',
    )
    mail_spf_record = forms.CharField(
        max_length=1000,
        required=False,
        label='SPF Sollwert',
        help_text='Dokumentierter DNS-Sollwert. Das Speichern ändert den öffentlichen DNS-Eintrag nicht.',
    )
    mail_dkim_selector = forms.CharField(
        max_length=120,
        required=False,
        label='DKIM-Selector',
        help_text='Optionaler Selector bzw. Hinweis auf die verwendeten Microsoft-365-DKIM-Selectoren.',
    )
    mail_dkim_record = forms.CharField(
        max_length=4000,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        label='DKIM DNS Sollwert',
        help_text='TXT-/CNAME-Sollwert oder beide Microsoft-365-DKIM-CNAMEs. Reine Dokumentation; DNS wird nicht automatisch verändert.',
    )
    mail_dmarc_record = forms.CharField(
        max_length=1000,
        required=False,
        label='DMARC Sollwert',
        help_text='Dokumentierter DNS-Sollwert für _dmarc.<Domain>.',
    )
    smtp_host = forms.CharField(
        max_length=253,
        required=False,
        label='SMTP 1 – Server',
        help_text='Zum Beispiel smtp.ionos.de.',
    )
    smtp_port = forms.IntegerField(
        min_value=1,
        max_value=65535,
        required=False,
        label='SMTP 1 – Port',
        help_text='Für IONOS mit STARTTLS: 587.',
    )
    smtp_use_tls = forms.BooleanField(
        required=False,
        label='SMTP 1 – STARTTLS verwenden',
    )
    smtp_username = forms.CharField(
        max_length=254,
        required=False,
        label='SMTP 1 – Benutzername',
        help_text='Bei IONOS normalerweise die vollständige E-Mail-Adresse.',
    )
    smtp_password = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label='SMTP 1 – Passwort',
        help_text='Leer lassen, um das gespeicherte Passwort unverändert zu lassen.',
    )
    smtp2_host = forms.CharField(
        max_length=253,
        required=False,
        label='SMTP 2 – Server',
        help_text='Optionaler zweiter SMTP-Provider, z. B. derselbe Relay-Dienst wie bei Listmonk.',
    )
    smtp2_port = forms.IntegerField(
        min_value=1,
        max_value=65535,
        required=False,
        label='SMTP 2 – Port',
        initial=587,
    )
    smtp2_use_tls = forms.BooleanField(
        required=False,
        label='SMTP 2 – STARTTLS verwenden',
        initial=True,
    )
    smtp2_username = forms.CharField(
        max_length=254,
        required=False,
        label='SMTP 2 – Benutzername',
    )
    smtp2_password = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label='SMTP 2 – Passwort',
        help_text='Leer lassen, um das gespeicherte Passwort unverändert zu lassen.',
    )
    graph_tenant_id = forms.CharField(
        max_length=120,
        required=False,
        label='Entra Tenant ID',
        help_text='Verzeichnis-/Mandanten-ID des Microsoft-365-Tenants.',
    )
    graph_client_id = forms.CharField(
        max_length=120,
        required=False,
        label='Entra Client ID',
        help_text='Anwendungs-/Client-ID der App-Registrierung.',
    )
    graph_sender = forms.EmailField(
        required=False,
        label='Microsoft-365-Absender',
        help_text='Postfach, über das Microsoft Graph senden soll, z. B. promptmaster@netstyle.de.',
    )
    graph_client_secret = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label='Entra Client Secret',
        help_text='Leer lassen, um das gespeicherte Secret unverändert zu lassen.',
    )
    disk_warning = forms.IntegerField(min_value=1, max_value=99, initial=80, label='Datenträger-Warnung in %')
    disk_critical = forms.IntegerField(min_value=2, max_value=100, initial=90, label='Datenträger kritisch in %')
    ram_warning = forms.IntegerField(min_value=1, max_value=99, initial=80, label='RAM-Warnung in %')
    ram_critical = forms.IntegerField(min_value=2, max_value=100, initial=90, label='RAM kritisch in %')
    cpu_warning = forms.IntegerField(min_value=1, max_value=100, initial=80, label='CPU-Warnung in %')
    backup_warning_hours = forms.IntegerField(min_value=1, max_value=720, initial=8, label='Backup-Warnung in Stunden')
    backup_critical_hours = forms.IntegerField(min_value=2, max_value=720, initial=24, label='Backup kritisch in Stunden')
    restore_warning_days = forms.IntegerField(min_value=1, max_value=365, initial=35, label='Restore-Test-Warnung in Tagen')

    def __init__(self, *args, graph_secret_configured=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph_secret_configured = graph_secret_configured

    def clean_ops_alert_recipients(self):
        raw = self.cleaned_data.get('ops_alert_recipients', '')
        parts = [
            item.strip().lower()
            for item in raw.replace(';', '\n').replace(',', '\n').splitlines()
            if item.strip()
        ]
        validator = forms.EmailField()
        normalized = []
        for item in parts:
            email = validator.clean(item)
            if email not in normalized:
                normalized.append(email)
        return '\n'.join(normalized)

    def clean_mail_domain(self):
        value = self.cleaned_data.get('mail_domain', '').strip().lower().rstrip('.')
        if value and ('@' in value or ' ' in value or '.' not in value):
            raise forms.ValidationError('Bitte eine gültige Domain ohne @ eingeben.')
        return value

    def clean_mail_spf_record(self):
        value = self.cleaned_data.get('mail_spf_record', '').strip()
        if value and not value.lower().startswith('v=spf1 '):
            raise forms.ValidationError('Ein SPF-Eintrag muss mit "v=spf1 " beginnen.')
        return value

    def clean_mail_dmarc_record(self):
        value = self.cleaned_data.get('mail_dmarc_record', '').strip()
        if value and not value.lower().startswith('v=dmarc1;'):
            raise forms.ValidationError('Ein DMARC-Eintrag muss mit "v=DMARC1;" beginnen.')
        return value

    def clean(self):
        data = super().clean()
        for warning, critical in [('disk_warning', 'disk_critical'), ('ram_warning', 'ram_critical'), ('backup_warning_hours', 'backup_critical_hours')]:
            if data.get(warning) is not None and data.get(critical) is not None and data[warning] >= data[critical]:
                self.add_error(critical, 'Der kritische Wert muss über dem Warnwert liegen.')
        mail_config_submitted = any(
            field in self.data
            for field in (
                'mail_delivery_mode',
                'mail_provider',
                'mail_fallback_1',
                'mail_fallback_2',
            )
        )
        mode = data.get('mail_delivery_mode') or 'manual'
        provider = data.get('mail_provider') or 'smtp1'
        fallback_1 = data.get('mail_fallback_1') or ''
        fallback_2 = data.get('mail_fallback_2') or ''
        route = [provider]
        if mail_config_submitted:
            if mode == 'failover':
                for fallback in (fallback_1, fallback_2):
                    if fallback:
                        route.append(fallback)
                if len(route) == 1:
                    self.add_error(
                        'mail_fallback_1',
                        'Für den automatischen Modus muss mindestens ein Fallback gewählt werden.',
                    )
            duplicates = {item for item in route if route.count(item) > 1}
            if duplicates:
                self.add_error(
                    'mail_fallback_1',
                    'Ein Versandweg darf in der Kette nur einmal vorkommen.',
                )

            if 'smtp1' in route:
                for field in ('smtp_host', 'smtp_port'):
                    if not data.get(field):
                        self.add_error(field, 'Für SMTP 1 ist dieses Feld erforderlich.')
            if 'smtp2' in route:
                for field in ('smtp2_host', 'smtp2_port'):
                    if not data.get(field):
                        self.add_error(field, 'Für SMTP 2 ist dieses Feld erforderlich.')
            if 'graph' in route:
                for field in ('graph_tenant_id', 'graph_client_id', 'graph_sender'):
                    if not data.get(field):
                        self.add_error(field, 'Für Microsoft Graph ist dieses Feld erforderlich.')
                if not data.get('graph_client_secret') and not self.graph_secret_configured:
                    self.add_error(
                        'graph_client_secret',
                        'Für Microsoft Graph ist ein Client Secret erforderlich.',
                    )

        from_email = data.get('mail_from_email')
        mail_domain = data.get('mail_domain')
        if from_email and mail_domain:
            sender_domain = from_email.rsplit('@', 1)[-1].lower()
            if sender_domain != mail_domain:
                self.add_error(
                    'mail_domain',
                    'Die Mail-Domain muss zur Absender-E-Mail passen.',
                )
        return data


class RefundForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea, required=False, max_length=2000, label='Begründung optional')
    confirm = forms.BooleanField(label='Erstattung verbindlich über Mollie auslösen')


class IntegrationSecretForm(forms.Form):
    value = forms.CharField(widget=forms.PasswordInput(render_value=False), max_length=500, label='Neuer Schlüssel')
