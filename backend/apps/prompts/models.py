from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class MicrosoftTier(TimeStampedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    rank = models.PositiveSmallIntegerField(unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['rank']

    def __str__(self):
        return self.name


class PromptApplication(TimeStampedModel):
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    group = models.CharField(max_length=80, default='m365')
    icon = models.CharField(max_length=12, blank=True)
    color = models.CharField(max_length=24, blank=True)
    description = models.TextField(blank=True)
    access_text = models.TextField(blank=True)
    status = models.CharField(max_length=40, blank=True)
    target = models.CharField(max_length=200, blank=True)
    rule = models.TextField(blank=True)
    evidence = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class PromptDefinition(TimeStampedModel):
    task_id = models.CharField(max_length=40, unique=True)
    application = models.ForeignKey(PromptApplication, on_delete=models.PROTECT, related_name='definitions')
    active = models.BooleanField(default=True)
    legacy = models.BooleanField(default=False)

    class Meta:
        ordering = ['task_id']
        indexes = [models.Index(fields=['application', 'active'])]

    def __str__(self):
        return self.task_id


class PromptPolicySet(TimeStampedModel):
    name = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=False)
    source_labels = models.JSONField(default=dict)
    source_instructions = models.JSONField(default=dict)
    method_rules = models.JSONField(default=dict)
    quality_rules = models.JSONField(default=dict)
    tone_rules = models.JSONField(default=dict)
    detail_rules = models.JSONField(default=dict)
    no_fabrication_rule = models.TextField()
    source_sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'version'], name='uniq_prompt_policy_name_version'),
            models.UniqueConstraint(fields=['active'], condition=Q(active=True), name='uniq_active_prompt_policy'),
        ]
        ordering = ['-version']

    def __str__(self):
        return f'{self.name} v{self.version}'


class PromptVersion(TimeStampedModel):
    LIFECYCLE = [
        ('DRAFT', 'Draft'),
        ('TEST', 'Test'),
        ('REVIEW', 'Review'),
        ('APPROVED', 'Approved'),
        ('PUBLISHED', 'Published'),
        ('ARCHIVED', 'Archived'),
    ]

    definition = models.ForeignKey(PromptDefinition, on_delete=models.CASCADE, related_name='versions')
    policy_set = models.ForeignKey(PromptPolicySet, on_delete=models.PROTECT, related_name='prompt_versions')
    version = models.PositiveIntegerField(default=1)
    lifecycle = models.CharField(max_length=20, choices=LIFECYCLE, default='DRAFT')
    title = models.CharField(max_length=240)
    area = models.CharField(max_length=120, blank=True)
    family = models.CharField(max_length=80)
    intent = models.TextField()
    access = models.JSONField(null=True, blank=True)
    product_status = models.CharField(max_length=40, blank=True)
    max_chars = models.PositiveIntegerField(null=True, blank=True)
    context_template = models.TextField(blank=True)
    app_rule_snapshot = models.TextField(blank=True)
    source_sha256 = models.CharField(max_length=64)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['definition', 'version'], name='uniq_prompt_definition_version'),
            models.UniqueConstraint(
                fields=['definition'],
                condition=Q(lifecycle='PUBLISHED'),
                name='uniq_published_prompt_version',
            ),
        ]
        ordering = ['definition__task_id', '-version']

    def __str__(self):
        return f'{self.definition.task_id} v{self.version}'


class PromptField(TimeStampedModel):
    KIND = [('required', 'Pflicht'), ('optional', 'Optional')]

    version = models.ForeignKey(PromptVersion, on_delete=models.CASCADE, related_name='fields')
    label = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=KIND)
    sort_order = models.PositiveIntegerField(default=0)
    optional_fragment = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['version', 'kind', 'sort_order'], name='uniq_prompt_field_order'),
            models.UniqueConstraint(fields=['version', 'label'], name='uniq_prompt_field_label'),
        ]
        ordering = ['kind', 'sort_order']

    @property
    def required(self):
        return self.kind == 'required'

    def __str__(self):
        return f'{self.version} · {self.label}'


class PromptOption(TimeStampedModel):
    KIND = [
        ('source', 'Quelle'),
        ('output', 'Ausgabeformat'),
        ('focus', 'Schwerpunkt'),
        ('audience', 'Zielgruppe'),
    ]

    version = models.ForeignKey(PromptVersion, on_delete=models.CASCADE, related_name='options')
    kind = models.CharField(max_length=20, choices=KIND)
    value = models.CharField(max_length=240)
    label = models.CharField(max_length=240)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['version', 'kind', 'value'], name='uniq_prompt_option_value'),
        ]
        ordering = ['kind', 'sort_order']

    def __str__(self):
        return f'{self.version} · {self.kind}: {self.value}'


class MicrosoftCapability(TimeStampedModel):
    SCOPE = [('application', 'Anwendung'), ('task', 'Aufgabe')]

    code = models.CharField(max_length=160, unique=True)
    name = models.CharField(max_length=220)
    scope = models.CharField(max_length=20, choices=SCOPE)
    application = models.ForeignKey(
        PromptApplication,
        on_delete=models.CASCADE,
        related_name='microsoft_capabilities',
        null=True,
        blank=True,
    )
    definition = models.ForeignKey(
        PromptDefinition,
        on_delete=models.CASCADE,
        related_name='microsoft_capabilities',
        null=True,
        blank=True,
    )
    minimum_tier = models.ForeignKey(MicrosoftTier, on_delete=models.PROTECT, related_name='capabilities')
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope='application', application__isnull=False, definition__isnull=True)
                    | Q(scope='task', application__isnull=True, definition__isnull=False)
                ),
                name='microsoft_capability_scope_target',
            ),
        ]

    def clean(self):
        if self.scope == 'application' and (not self.application_id or self.definition_id):
            raise ValidationError('Application-Capability benötigt genau eine Anwendung.')
        if self.scope == 'task' and (not self.definition_id or self.application_id):
            raise ValidationError('Task-Capability benötigt genau eine PromptDefinition.')

    def __str__(self):
        return self.name


class PromptLegacyContract(TimeStampedModel):
    SOURCE = [
        ('FREE_1_2_4', 'Free 1.2.4'),
        ('PM11_1_1', 'Pro PM11 1.1'),
    ]
    MAPPING = [('unmapped', 'Nicht gemappt'), ('mapped', 'Gemappt'), ('superseded', 'Ersetzt')]

    source = models.CharField(max_length=30, choices=SOURCE)
    legacy_id = models.CharField(max_length=80)
    application_code = models.CharField(max_length=80, blank=True)
    title = models.CharField(max_length=240)
    payload = models.JSONField(default=dict)
    mapping_status = models.CharField(max_length=20, choices=MAPPING, default='unmapped')
    target_definition = models.ForeignKey(
        PromptDefinition,
        on_delete=models.SET_NULL,
        related_name='legacy_contracts',
        null=True,
        blank=True,
    )
    source_sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['source', 'legacy_id'], name='uniq_prompt_legacy_contract'),
        ]
        ordering = ['source', 'legacy_id']

    def __str__(self):
        return f'{self.source}:{self.legacy_id}'


class PromptTestCase(TimeStampedModel):
    STATUS = [
        ('NEVER', 'Noch nicht ausgeführt'),
        ('PASSED', 'Bestanden'),
        ('FAILED', 'Fehlgeschlagen'),
        ('ERROR', 'Fehler'),
    ]

    version = models.ForeignKey(PromptVersion, on_delete=models.CASCADE, related_name='test_cases')
    name = models.CharField(max_length=200)
    input_payload = models.JSONField(default=dict)
    expected_contains = models.JSONField(default=list, blank=True)
    expected_not_contains = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    last_status = models.CharField(max_length=20, choices=STATUS, default='NEVER')
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['version', 'name'], name='uniq_prompt_testcase_name'),
        ]
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f'{self.version} · {self.name}'


class PromptRating(TimeStampedModel):
    version = models.ForeignKey(PromptVersion, on_delete=models.CASCADE, related_name='ratings')
    definition = models.ForeignKey(PromptDefinition, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='prompt_ratings',
    )
    stars = models.PositiveSmallIntegerField()
    feedback = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['version', 'user'], name='uniq_prompt_rating_user_version'),
            models.CheckConstraint(condition=Q(stars__gte=1) & Q(stars__lte=5), name='prompt_rating_1_to_5'),
        ]
        indexes = [
            models.Index(fields=['definition', '-created_at']),
            models.Index(fields=['version', '-created_at']),
        ]
        ordering = ['-updated_at']

    def clean(self):
        if self.version_id and self.definition_id and self.version.definition_id != self.definition_id:
            raise ValidationError('Bewertung und Prompt-Version gehören nicht zur selben PromptDefinition.')
        if self.stars and not 1 <= int(self.stars) <= 5:
            raise ValidationError({'stars': 'Bewertung muss zwischen 1 und 5 Sternen liegen.'})
        if self.stars and int(self.stars) >= 4:
            self.feedback = ''

    def __str__(self):
        return f'{self.definition.task_id} · {self.stars}★'


class PromptQualityPolicy(TimeStampedModel):
    name = models.CharField(max_length=120, default='Standard')
    active = models.BooleanField(default=False)
    minimum_average = models.DecimalField(max_digits=3, decimal_places=2, default=3.80)
    critical_average = models.DecimalField(max_digits=3, decimal_places=2, default=3.20)
    warning_drop = models.DecimalField(max_digits=3, decimal_places=2, default=0.40)
    critical_drop = models.DecimalField(max_digits=3, decimal_places=2, default=0.80)
    recent_sample_size = models.PositiveSmallIntegerField(default=30)
    previous_sample_size = models.PositiveSmallIntegerField(default=30)
    minimum_samples = models.PositiveSmallIntegerField(default=5)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['active'], condition=Q(active=True), name='uniq_active_prompt_quality_policy'),
            models.CheckConstraint(condition=Q(minimum_average__gte=1) & Q(minimum_average__lte=5), name='quality_min_avg_1_5'),
            models.CheckConstraint(condition=Q(critical_average__gte=1) & Q(critical_average__lte=5), name='quality_critical_avg_1_5'),
        ]

    def clean(self):
        if self.critical_average > self.minimum_average:
            raise ValidationError({'critical_average': 'Kritische Schwelle muss kleiner/gleich Warnschwelle sein.'})
        if self.minimum_samples < 1:
            raise ValidationError({'minimum_samples': 'Mindestens ein Sample erforderlich.'})

    def __str__(self):
        return self.name


class PromptQualitySnapshot(TimeStampedModel):
    STATUS = [('OK', 'OK'), ('WATCH', 'Beobachten'), ('WARN', 'Warnung'), ('CRITICAL', 'Kritisch')]

    definition = models.ForeignKey(PromptDefinition, on_delete=models.CASCADE, related_name='quality_snapshots')
    version = models.ForeignKey(PromptVersion, on_delete=models.CASCADE, related_name='quality_snapshots')
    policy = models.ForeignKey(PromptQualityPolicy, on_delete=models.PROTECT, related_name='snapshots')
    status = models.CharField(max_length=20, choices=STATUS, default='WATCH')
    rating_count = models.PositiveIntegerField(default=0)
    recent_count = models.PositiveIntegerField(default=0)
    previous_count = models.PositiveIntegerField(default=0)
    recent_average = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    previous_average = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    average_drop = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    calculated_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['status', '-calculated_at']),
            models.Index(fields=['definition', '-calculated_at']),
        ]
        ordering = ['-calculated_at']

    def __str__(self):
        return f'{self.definition.task_id} · {self.status} · {self.calculated_at}'
