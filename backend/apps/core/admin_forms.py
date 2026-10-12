from decimal import Decimal

from django import forms
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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
        label=_("Zuständig"),
        empty_label=_("Nicht zugewiesen"),
    )

    class Meta:
        model = Lead
        fields = [
            'kind', 'company_name', 'first_name', 'last_name', 'email', 'phone',
            'source', 'status', 'priority', 'assigned_to', 'next_action_at', 'notes',
        ]
        labels = {
            'kind': _("Lead-Typ"),
            'company_name': _("Unternehmen"),
            'first_name': _("Vorname"),
            'last_name': _("Nachname"),
            'email': _("E-Mail"),
            'phone': _("Telefon"),
            'source': _("Quelle"),
            'status': _("Status"),
            'priority': _("Priorität"),
            'next_action_at': _("Nächste Aktion"),
            'notes': _("Interne Notizen"),
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
            self.add_error('company_name', _("Für Unternehmens-Leads ist der Unternehmensname erforderlich."))
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
                _("Für diese E-Mail-Adresse existiert bereits ein aktiver Lead.")
            )
        return value


class LeadAssignForm(forms.Form):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label=_("Zuständig"),
        empty_label=_("Nicht zugewiesen"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(
            is_staff=True,
            is_active=True,
        ).order_by('last_name', 'first_name', 'email')


class LeadDeleteForm(forms.Form):
    confirm = forms.BooleanField(
        label=_("Lead wirklich löschen"),
        help_text=_("Der Datensatz wird revisionssicher ausgeblendet und im Audit protokolliert."),
    )


class LeadConvertCompanyForm(forms.Form):
    company_name = forms.CharField(max_length=200, label=_("Unternehmensname"))
    legal_form = forms.CharField(max_length=80, required=False, label=_("Rechtsform"))
    email = forms.EmailField(label=_("E-Mail des Firmenadministrators"))
    first_name = forms.CharField(max_length=120, label=_("Vorname"))
    last_name = forms.CharField(max_length=120, label=_("Nachname"))
    phone = forms.CharField(max_length=60, required=False, label=_("Telefon"))
    street = forms.CharField(max_length=160, required=False, label=_("Straße"))
    house_number = forms.CharField(max_length=40, required=False, label=_("Hausnummer"))
    postal_code = forms.CharField(max_length=20, required=False, label=_("PLZ"))
    city = forms.CharField(max_length=120, required=False, label=_("Ort"))
    country = forms.CharField(max_length=2, initial='DE', label=_("Land"))
    vat_id = forms.CharField(max_length=40, required=False, label=_("USt-IdNr."))
    tax_number = forms.CharField(max_length=60, required=False, label=_("Steuernummer"))
    confirm = forms.BooleanField(
        label=_("Lead in Firmenkunden umwandeln und Einladungslink senden"),
    )


    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(
                _("Diese E-Mail-Adresse gehört bereits zu einem PROMPTFINISHER-Konto.")
            )
        if Company.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(
                _("Diese E-Mail-Adresse ist bereits einem Firmenkunden zugeordnet.")
            )
        return value


class CustomerAdminInviteForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail des Firmenadministrators"))
    first_name = forms.CharField(max_length=120, label=_("Vorname"))
    last_name = forms.CharField(max_length=120, label=_("Nachname"))

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(
                _("Diese E-Mail-Adresse gehört bereits zu einem PROMPTFINISHER-Konto.")
            )
        return value


class SupportAdminTransferForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        label=_("Eigenes Passwort erneut eingeben"),
        help_text=_("Sicherheitsbestätigung des aktuell angemeldeten netstyle Benutzers."),
    )
    identity_verified = forms.BooleanField(
        required=True,
        label=_("Identität und Berechtigung des Ansprechpartners wurden geprüft"),
    )
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={'rows': 3}),
        label=_("Interne Notiz zur Prüfung (optional)"),
    )


class AdminCompanyForm(CompanyForm):
    class Meta(CompanyForm.Meta):
        fields = CompanyForm.Meta.fields + ['status']


class ProductForm(forms.ModelForm):
    features = forms.ModelMultipleChoiceField(
        queryset=Feature.objects.none(), required=False, widget=forms.CheckboxSelectMultiple,
        label=_("Features / Entitlements"),
    )

    class Meta:
        model = Product
        fields = [
            'code', 'name', 'description', 'active', 'visible', 'purchasable',
            'default_license_days', 'default_device_limit', 'reminder_1_days',
            'reminder_2_days', 'critical_warning_days',
        ]
        labels = {
            'code': _("Produktcode"),
            'name': _("Name"),
            'description': _("Beschreibung"),
            'active': _("Aktiv"),
            'visible': _("Sichtbar"),
            'purchasable': _("Kaufbar"),
            'default_license_days': _("Standard-Laufzeit in Tagen"),
            'default_device_limit': _("Geräte je Benutzer"),
            'reminder_1_days': _("Erinnerung 1 · Tage vorher"),
            'reminder_2_days': _("Erinnerung 2 · Tage vorher"),
            'critical_warning_days': _("Kritische Warnung · Tage vorher"),
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
            self.add_error('reminder_1_days', _("Reminder 1 muss vor Reminder 2 liegen (größere Tageszahl)."))
        if None not in (r2, critical) and r2 <= critical:
            self.add_error('reminder_2_days', _("Reminder 2 muss vor der kritischen Warnphase liegen."))
        return data


class FeatureForm(forms.ModelForm):
    class Meta:
        model = Feature
        fields = ['code', 'name']
        labels = {'code': 'Code', 'name': 'Name'}

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class PriceVersionForm(forms.Form):
    price_type = forms.ChoiceField(label=_("Preistyp"), choices=[('new', _("Neukauf")), ('renewal', _("Verlängerung"))])
    gross_amount = forms.DecimalField(min_value=Decimal('0.00'), decimal_places=2, max_digits=10, label=_("Bruttopreis"))
    currency = forms.CharField(max_length=3, initial='EUR', label=_("Währung"))
    valid_from = forms.DateTimeField(initial=timezone.now, label=_("Gültig ab"))

    def clean_currency(self):
        return self.cleaned_data['currency'].strip().upper()


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ['subject', 'body_text', 'active']
        labels = {'subject': _('Betreff'), 'body_text': _('Nachrichtentext'), 'active': _('Aktiv')}


class ServiceAccountForm(forms.Form):
    SCOPE_CHOICES = [
        ('ops.read', _("Operations lesen")),
        ('prompt.read', _("Prompts lesen")),
        ('prompt.draft', _("Prompt-Drafts erzeugen")),
        ('prompt.test', _("Prompt-Tests ausführen")),
    ]
    name = forms.CharField(max_length=120, label=_("Name"))
    scopes = forms.MultipleChoiceField(label=_("Berechtigungen"), choices=SCOPE_CHOICES, initial=['ops.read'])
    expires_at = forms.DateTimeField(required=False, label=_("Ablauf optional"))


class LegalDocumentForm(forms.ModelForm):
    class Meta:
        model = LegalDocument
        fields = ['doc_type', 'version', 'content', 'valid_from', 'active']
        labels = {
            'doc_type': _("Dokumenttyp"),
            'version': _("Version"),
            'content': _("Inhalt"),
            'valid_from': _("Gültig ab"),
            'active': _("Aktiv"),
        }


class RetentionPolicyForm(forms.ModelForm):
    class Meta:
        model = RetentionPolicy
        fields = ['data_class', 'retain_days', 'active']
        labels = {'data_class': 'Datenklasse', 'retain_days': 'Aufbewahrung in Tagen', 'active': 'Aktiv'}
        help_texts = {
            'data_class': _("Unterstützt: expired_invitations, email_messages, revoked_devices, resolved_system_alerts, resolved_task_failures, expired_sessions."),
            'retain_days': _("Löschung erst nach dieser Anzahl Tage. Rechtliche Aufbewahrungsfristen separat prüfen."),
        }

    ALLOWED_DATA_CLASSES = {
        'expired_invitations', 'email_messages', 'revoked_devices',
        'resolved_system_alerts', 'resolved_task_failures', 'expired_sessions',
    }

    def clean_data_class(self):
        value = self.cleaned_data['data_class'].strip()
        if value not in self.ALLOWED_DATA_CLASSES:
            raise forms.ValidationError(_("Für diese Datenklasse existiert kein freigegebener Lösch-Handler."))
        return value


class DeletionRejectForm(forms.Form):
    notes = forms.CharField(widget=forms.Textarea, max_length=5000, label=_("Begründung"))


PERMISSION_DOMAIN_LABELS = {
    'customers': _("Kunden"),
    'leads': _("Leads"),
    'licenses': _("Lizenzen"),
    'devices': _("Geräte"),
    'orders': _("Bestellungen"),
    'payments': _("Zahlungen"),
    'products': _("Produkte & Preise"),
    'email': _("E-Mail"),
    'ops': _("System & Betrieb"),
    'api': _("API & Integrationen"),
    'roles': _("Benutzer & Rollen"),
    'legal': _("Datenschutz & Recht"),
    'support': _("Kontaktanfragen"),
    'audit': _("Protokolle"),
    'settings': _("Einstellungen"),
    'prompts': _("Prompt Studio"),
    'content': _("FAQ & Inhalte"),
}
PERMISSION_ACTION_LABELS = {
    'read': _("Lesen"),
    'assign': _("Zuweisen"),
    'convert': _("In Kunde umwandeln"),
    'delete': _("Löschen"),
    'write': _("Bearbeiten"),
    'refund': _("Erstatten"),
    'compose': _("Prompts erzeugen"),
    'publish': _("Veröffentlichen"),
    'quality': _("Qualität verwalten"),
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
        label=_("Berechtigungen"),
    )

    class Meta:
        model = Role
        fields = ['name', 'active', 'permissions']
        labels = {'name': _('Rollenname'), 'active': _('Aktiv')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].queryset = Permission.objects.order_by('code')


class StaffUserCreateForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail"))
    first_name = forms.CharField(max_length=120, label=_("Vorname"))
    last_name = forms.CharField(max_length=120, label=_("Nachname"))
    role = forms.ModelChoiceField(queryset=Role.objects.none(), label=_("Rolle"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].queryset = Role.objects.filter(active=True).order_by('name')

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(_("Diese E-Mail-Adresse ist bereits registriert."))
        return value


class StaffUserRoleForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), label=_("Benutzer"))
    role = forms.ModelChoiceField(queryset=Role.objects.none(), label=_("Rolle"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(is_staff=True, is_active=True).order_by('email')
        self.fields['role'].queryset = Role.objects.filter(active=True).order_by('name')


class MollieConfigForm(forms.Form):
    profile_id = forms.CharField(max_length=120, required=False, label=_("Profile ID"))
    api_key = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label=_("API-Schlüssel"),
        help_text=_("Leer lassen, um den bestehenden Schlüssel unverändert zu lassen."),
    )

    def clean_api_key(self):
        key = (self.cleaned_data.get('api_key') or '').strip()
        if not key:
            return ''
        environment = str(getattr(settings, 'ENVIRONMENT', 'development') or '').strip().lower()
        if environment == 'production':
            if not key.startswith('live_'):
                raise forms.ValidationError(
                    _("In Produktion ist ausschließlich ein Mollie-Live-Key (live_…) zulässig.")
                )
        elif not key.startswith('test_'):
            raise forms.ValidationError(
                _("Außerhalb der Produktion ist ausschließlich ein Mollie-Test-Key (test_…) zulässig.")
            )
        return key


class GeneralSettingsForm(forms.Form):
    MAIL_PROVIDER_CHOICES = [
        ('smtp1', 'SMTP 1'),
        ('smtp2', 'SMTP 2'),
        ('graph', 'Microsoft 365 / Entra ID (Microsoft Graph)'),
    ]
    MAIL_FALLBACK_CHOICES = [
        ('', _("Kein weiterer Fallback")),
        *MAIL_PROVIDER_CHOICES,
    ]
    MAIL_DELIVERY_MODE_CHOICES = [
        ('manual', _("Manuell – nur den primären Versandweg verwenden")),
        ('failover', _("Automatisch – bei sicherem Ausfall auf Fallback wechseln")),
    ]

    support_email = forms.EmailField(label=_("Support-Empfänger"))
    ops_alert_recipients = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        label=_("Monitoring-Alarmempfänger"),
        help_text=_("Eine oder mehrere E-Mail-Adressen, getrennt durch Zeilenumbruch, Komma oder Semikolon."),
    )
    mail_delivery_mode = forms.ChoiceField(
        choices=MAIL_DELIVERY_MODE_CHOICES,
        required=False,
        label=_("Versandmodus"),
        help_text=_("Im automatischen Modus wird nur bei eindeutig nicht zugestellten Fehlern weitergeschaltet."),
    )
    mail_provider = forms.ChoiceField(
        choices=MAIL_PROVIDER_CHOICES,
        required=False,
        label=_("Primärer Versandweg"),
        help_text=_("SMTP 1, SMTP 2 und Microsoft Graph bleiben parallel konfiguriert."),
    )
    mail_fallback_1 = forms.ChoiceField(
        choices=MAIL_FALLBACK_CHOICES,
        required=False,
        label=_("Fallback 1"),
    )
    mail_fallback_2 = forms.ChoiceField(
        choices=MAIL_FALLBACK_CHOICES,
        required=False,
        label=_("Fallback 2"),
    )
    mail_from_email = forms.EmailField(
        required=False,
        label=_("Absender-E-Mail"),
        help_text=_("Aktive Absenderadresse für SMTP. Änderungen gelten ohne Container-Neustart."),
    )
    mail_from_name = forms.CharField(
        max_length=120,
        required=False,
        label=_("Absender-Anzeigename"),
        help_text=_("Zum Beispiel PROMPTFINISHER."),
    )
    mail_reply_to = forms.EmailField(
        required=False,
        label=_("Antwortadresse"),
        help_text=_("Optional. Leer lassen, wenn Antworten an die Absenderadresse gehen sollen."),
    )
    mail_domain = forms.CharField(
        max_length=253,
        required=False,
        label=_("Mail-Domain"),
        help_text=_("Domain des sichtbaren Absenders, z. B. decke-wand-boden.de oder später promptmaster.ai."),
    )
    mail_spf_record = forms.CharField(
        max_length=1000,
        required=False,
        label=_("SPF Sollwert"),
        help_text=_("Dokumentierter DNS-Sollwert. Das Speichern ändert den öffentlichen DNS-Eintrag nicht."),
    )
    mail_dkim_selector = forms.CharField(
        max_length=120,
        required=False,
        label=_("DKIM-Selector"),
        help_text=_("Optionaler Selector bzw. Hinweis auf die verwendeten Microsoft-365-DKIM-Selectoren."),
    )
    mail_dkim_record = forms.CharField(
        max_length=4000,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        label=_("DKIM DNS Sollwert"),
        help_text=_("TXT-/CNAME-Sollwert oder beide Microsoft-365-DKIM-CNAMEs. Reine Dokumentation; DNS wird nicht automatisch verändert."),
    )
    mail_dmarc_record = forms.CharField(
        max_length=1000,
        required=False,
        label=_("DMARC Sollwert"),
        help_text=_("Dokumentierter DNS-Sollwert für _dmarc.<Domain>."),
    )
    smtp_host = forms.CharField(
        max_length=253,
        required=False,
        label=_("SMTP 1 – Server"),
        help_text=_("Zum Beispiel smtp.ionos.de."),
    )
    smtp_port = forms.IntegerField(
        min_value=1,
        max_value=65535,
        required=False,
        label=_("SMTP 1 – Port"),
        help_text=_("Für IONOS mit STARTTLS: 587."),
    )
    smtp_use_tls = forms.BooleanField(
        required=False,
        label=_("SMTP 1 – STARTTLS verwenden"),
    )
    smtp_username = forms.CharField(
        max_length=254,
        required=False,
        label=_("SMTP 1 – Benutzername"),
        help_text=_("Bei IONOS normalerweise die vollständige E-Mail-Adresse."),
    )
    smtp_password = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label=_("SMTP 1 – Passwort"),
        help_text=_("Leer lassen, um das gespeicherte Passwort unverändert zu lassen."),
    )
    smtp2_host = forms.CharField(
        max_length=253,
        required=False,
        label=_("SMTP 2 – Server"),
        help_text=_("Optionaler zweiter SMTP-Provider, z. B. derselbe Relay-Dienst wie bei Listmonk."),
    )
    smtp2_port = forms.IntegerField(
        min_value=1,
        max_value=65535,
        required=False,
        label=_("SMTP 2 – Port"),
        initial=587,
    )
    smtp2_use_tls = forms.BooleanField(
        required=False,
        label=_("SMTP 2 – STARTTLS verwenden"),
        initial=True,
    )
    smtp2_username = forms.CharField(
        max_length=254,
        required=False,
        label=_("SMTP 2 – Benutzername"),
    )
    smtp2_password = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label=_("SMTP 2 – Passwort"),
        help_text=_("Leer lassen, um das gespeicherte Passwort unverändert zu lassen."),
    )
    graph_tenant_id = forms.CharField(
        max_length=120,
        required=False,
        label=_("Entra Tenant ID"),
        help_text=_("Verzeichnis-/Mandanten-ID des Microsoft-365-Tenants."),
    )
    graph_client_id = forms.CharField(
        max_length=120,
        required=False,
        label=_("Entra Client ID"),
        help_text=_("Anwendungs-/Client-ID der App-Registrierung."),
    )
    graph_sender = forms.EmailField(
        required=False,
        label=_("Microsoft-365-Absender"),
        help_text=_("Postfach, über das Microsoft Graph senden soll, z. B. promptmaster@netstyle.de."),
    )
    graph_client_secret = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label=_("Entra Client Secret"),
        help_text=_("Leer lassen, um das gespeicherte Secret unverändert zu lassen."),
    )
    disk_warning = forms.IntegerField(min_value=1, max_value=99, initial=80, label=_("Datenträger-Warnung in %"))
    disk_critical = forms.IntegerField(min_value=2, max_value=100, initial=90, label=_("Datenträger kritisch in %"))
    ram_warning = forms.IntegerField(min_value=1, max_value=99, initial=80, label=_("RAM-Warnung in %"))
    ram_critical = forms.IntegerField(min_value=2, max_value=100, initial=90, label=_("RAM kritisch in %"))
    cpu_warning = forms.IntegerField(min_value=1, max_value=100, initial=80, label=_("CPU-Warnung in %"))
    backup_warning_hours = forms.IntegerField(min_value=1, max_value=720, initial=8, label=_("Backup-Warnung in Stunden"))
    backup_critical_hours = forms.IntegerField(min_value=2, max_value=720, initial=24, label=_("Backup kritisch in Stunden"))
    restore_warning_days = forms.IntegerField(min_value=1, max_value=365, initial=35, label=_("Restore-Test-Warnung in Tagen"))

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
            raise forms.ValidationError(_("Bitte eine gültige Domain ohne @ eingeben."))
        return value

    def clean_mail_spf_record(self):
        value = self.cleaned_data.get('mail_spf_record', '').strip()
        if value and not value.lower().startswith('v=spf1 '):
            raise forms.ValidationError(_("Ein SPF-Eintrag muss mit \"v=spf1 \" beginnen."))
        return value

    def clean_mail_dmarc_record(self):
        value = self.cleaned_data.get('mail_dmarc_record', '').strip()
        if value and not value.lower().startswith('v=dmarc1;'):
            raise forms.ValidationError(_("Ein DMARC-Eintrag muss mit \"v=DMARC1;\" beginnen."))
        return value

    def clean(self):
        data = super().clean()
        for warning, critical in [('disk_warning', 'disk_critical'), ('ram_warning', 'ram_critical'), ('backup_warning_hours', 'backup_critical_hours')]:
            if data.get(warning) is not None and data.get(critical) is not None and data[warning] >= data[critical]:
                self.add_error(critical, _("Der kritische Wert muss über dem Warnwert liegen."))
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
                        _("Für den automatischen Modus muss mindestens ein Fallback gewählt werden."),
                    )
            duplicates = {item for item in route if route.count(item) > 1}
            if duplicates:
                self.add_error(
                    'mail_fallback_1',
                    _("Ein Versandweg darf in der Kette nur einmal vorkommen."),
                )

            if 'smtp1' in route:
                for field in ('smtp_host', 'smtp_port'):
                    if not data.get(field):
                        self.add_error(field, _("Für SMTP 1 ist dieses Feld erforderlich."))
            if 'smtp2' in route:
                for field in ('smtp2_host', 'smtp2_port'):
                    if not data.get(field):
                        self.add_error(field, _("Für SMTP 2 ist dieses Feld erforderlich."))
            if 'graph' in route:
                for field in ('graph_tenant_id', 'graph_client_id', 'graph_sender'):
                    if not data.get(field):
                        self.add_error(field, _("Für Microsoft Graph ist dieses Feld erforderlich."))
                if not data.get('graph_client_secret') and not self.graph_secret_configured:
                    self.add_error(
                        'graph_client_secret',
                        _("Für Microsoft Graph ist ein Client Secret erforderlich."),
                    )

        from_email = data.get('mail_from_email')
        mail_domain = data.get('mail_domain')
        if from_email and mail_domain:
            sender_domain = from_email.rsplit('@', 1)[-1].lower()
            if sender_domain != mail_domain:
                self.add_error(
                    'mail_domain',
                    _("Die Mail-Domain muss zur Absender-E-Mail passen."),
                )
        return data


class RefundForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea, required=False, max_length=2000, label=_("Begründung optional"))
    confirm = forms.BooleanField(label=_("Erstattung verbindlich über Mollie auslösen"))


class IntegrationSecretForm(forms.Form):
    value = forms.CharField(widget=forms.PasswordInput(render_value=False), max_length=500, label=_("Neuer Schlüssel"))
