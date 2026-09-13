import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='MicrosoftTier',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=40, unique=True)),
                ('name', models.CharField(max_length=160)),
                ('rank', models.PositiveSmallIntegerField(unique=True)),
                ('description', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['rank']},
        ),
        migrations.CreateModel(
            name='PromptApplication',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=80, unique=True)),
                ('name', models.CharField(max_length=160)),
                ('group', models.CharField(default='m365', max_length=80)),
                ('icon', models.CharField(blank=True, max_length=12)),
                ('color', models.CharField(blank=True, max_length=24)),
                ('description', models.TextField(blank=True)),
                ('access_text', models.TextField(blank=True)),
                ('status', models.CharField(blank=True, max_length=40)),
                ('target', models.CharField(blank=True, max_length=200)),
                ('rule', models.TextField(blank=True)),
                ('evidence', models.JSONField(blank=True, default=list)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['sort_order', 'name']},
        ),
        migrations.CreateModel(
            name='PromptPolicySet',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=120)),
                ('version', models.PositiveIntegerField(default=1)),
                ('active', models.BooleanField(default=False)),
                ('source_labels', models.JSONField(default=dict)),
                ('source_instructions', models.JSONField(default=dict)),
                ('method_rules', models.JSONField(default=dict)),
                ('quality_rules', models.JSONField(default=dict)),
                ('tone_rules', models.JSONField(default=dict)),
                ('detail_rules', models.JSONField(default=dict)),
                ('no_fabrication_rule', models.TextField()),
                ('source_sha256', models.CharField(max_length=64)),
            ],
            options={'ordering': ['-version']},
        ),
        migrations.CreateModel(
            name='PromptDefinition',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('task_id', models.CharField(max_length=40, unique=True)),
                ('active', models.BooleanField(default=True)),
                ('legacy', models.BooleanField(default=False)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='definitions', to='prompts.promptapplication')),
            ],
            options={'ordering': ['task_id']},
        ),
        migrations.CreateModel(
            name='PromptVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('lifecycle', models.CharField(choices=[('DRAFT', 'Draft'), ('TEST', 'Test'), ('REVIEW', 'Review'), ('APPROVED', 'Approved'), ('PUBLISHED', 'Published'), ('ARCHIVED', 'Archived')], default='DRAFT', max_length=20)),
                ('title', models.CharField(max_length=240)),
                ('area', models.CharField(blank=True, max_length=120)),
                ('family', models.CharField(max_length=80)),
                ('intent', models.TextField()),
                ('access', models.JSONField(blank=True, null=True)),
                ('product_status', models.CharField(blank=True, max_length=40)),
                ('max_chars', models.PositiveIntegerField(blank=True, null=True)),
                ('context_template', models.TextField(blank=True)),
                ('app_rule_snapshot', models.TextField(blank=True)),
                ('source_sha256', models.CharField(max_length=64)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('definition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='prompts.promptdefinition')),
                ('policy_set', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prompt_versions', to='prompts.promptpolicyset')),
            ],
            options={'ordering': ['definition__task_id', '-version']},
        ),
        migrations.CreateModel(
            name='PromptField',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('label', models.CharField(max_length=200)),
                ('kind', models.CharField(choices=[('required', 'Pflicht'), ('optional', 'Optional')], max_length=20)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('optional_fragment', models.TextField(blank=True)),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fields', to='prompts.promptversion')),
            ],
            options={'ordering': ['kind', 'sort_order']},
        ),
        migrations.CreateModel(
            name='PromptOption',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('source', 'Quelle'), ('output', 'Ausgabeformat'), ('focus', 'Schwerpunkt'), ('audience', 'Zielgruppe')], max_length=20)),
                ('value', models.CharField(max_length=240)),
                ('label', models.CharField(max_length=240)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='prompts.promptversion')),
            ],
            options={'ordering': ['kind', 'sort_order']},
        ),
        migrations.CreateModel(
            name='MicrosoftCapability',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=160, unique=True)),
                ('name', models.CharField(max_length=220)),
                ('scope', models.CharField(choices=[('application', 'Anwendung'), ('task', 'Aufgabe')], max_length=20)),
                ('description', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
                ('application', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='microsoft_capabilities', to='prompts.promptapplication')),
                ('definition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='microsoft_capabilities', to='prompts.promptdefinition')),
                ('minimum_tier', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='capabilities', to='prompts.microsofttier')),
            ],
        ),
        migrations.CreateModel(
            name='PromptLegacyContract',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source', models.CharField(choices=[('FREE_1_2_4', 'Free 1.2.4'), ('PM11_1_1', 'Pro PM11 1.1')], max_length=30)),
                ('legacy_id', models.CharField(max_length=80)),
                ('application_code', models.CharField(blank=True, max_length=80)),
                ('title', models.CharField(max_length=240)),
                ('payload', models.JSONField(default=dict)),
                ('mapping_status', models.CharField(choices=[('unmapped', 'Nicht gemappt'), ('mapped', 'Gemappt'), ('superseded', 'Ersetzt')], default='unmapped', max_length=20)),
                ('source_sha256', models.CharField(max_length=64)),
                ('target_definition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='legacy_contracts', to='prompts.promptdefinition')),
            ],
            options={'ordering': ['source', 'legacy_id']},
        ),
        migrations.AddIndex(
            model_name='promptdefinition',
            index=models.Index(fields=['application', 'active'], name='prompts_pro_applica_e75f93_idx'),
        ),
        migrations.AddConstraint(
            model_name='promptpolicyset',
            constraint=models.UniqueConstraint(fields=('name', 'version'), name='uniq_prompt_policy_name_version'),
        ),
        migrations.AddConstraint(
            model_name='promptpolicyset',
            constraint=models.UniqueConstraint(condition=Q(('active', True)), fields=('active',), name='uniq_active_prompt_policy'),
        ),
        migrations.AddConstraint(
            model_name='promptversion',
            constraint=models.UniqueConstraint(fields=('definition', 'version'), name='uniq_prompt_definition_version'),
        ),
        migrations.AddConstraint(
            model_name='promptversion',
            constraint=models.UniqueConstraint(condition=Q(('lifecycle', 'PUBLISHED')), fields=('definition',), name='uniq_published_prompt_version'),
        ),
        migrations.AddConstraint(
            model_name='promptfield',
            constraint=models.UniqueConstraint(fields=('version', 'kind', 'sort_order'), name='uniq_prompt_field_order'),
        ),
        migrations.AddConstraint(
            model_name='promptfield',
            constraint=models.UniqueConstraint(fields=('version', 'label'), name='uniq_prompt_field_label'),
        ),
        migrations.AddConstraint(
            model_name='promptoption',
            constraint=models.UniqueConstraint(fields=('version', 'kind', 'value'), name='uniq_prompt_option_value'),
        ),
        migrations.AddConstraint(
            model_name='microsoftcapability',
            constraint=models.CheckConstraint(
                condition=(Q(('application__isnull', False), ('definition__isnull', True), ('scope', 'application')) | Q(('application__isnull', True), ('definition__isnull', False), ('scope', 'task'))),
                name='microsoft_capability_scope_target',
            ),
        ),
        migrations.AddConstraint(
            model_name='promptlegacycontract',
            constraint=models.UniqueConstraint(fields=('source', 'legacy_id'), name='uniq_prompt_legacy_contract'),
        ),
    ]
