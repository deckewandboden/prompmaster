from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ('prompts', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PromptQualityPolicy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(default='Standard', max_length=120)),
                ('active', models.BooleanField(default=False)),
                ('minimum_average', models.DecimalField(decimal_places=2, default=3.8, max_digits=3)),
                ('critical_average', models.DecimalField(decimal_places=2, default=3.2, max_digits=3)),
                ('warning_drop', models.DecimalField(decimal_places=2, default=0.4, max_digits=3)),
                ('critical_drop', models.DecimalField(decimal_places=2, default=0.8, max_digits=3)),
                ('recent_sample_size', models.PositiveSmallIntegerField(default=30)),
                ('previous_sample_size', models.PositiveSmallIntegerField(default=30)),
                ('minimum_samples', models.PositiveSmallIntegerField(default=5)),
            ],
        ),
        migrations.CreateModel(
            name='PromptTestCase',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=200)),
                ('input_payload', models.JSONField(default=dict)),
                ('expected_contains', models.JSONField(blank=True, default=list)),
                ('expected_not_contains', models.JSONField(blank=True, default=list)),
                ('enabled', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('last_status', models.CharField(choices=[('NEVER', 'Noch nicht ausgeführt'), ('PASSED', 'Bestanden'), ('FAILED', 'Fehlgeschlagen'), ('ERROR', 'Fehler')], default='NEVER', max_length=20)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='test_cases', to='prompts.promptversion')),
            ],
            options={'ordering': ['sort_order', 'name']},
        ),
        migrations.CreateModel(
            name='PromptRating',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('stars', models.PositiveSmallIntegerField()),
                ('feedback', models.TextField(blank=True)),
                ('definition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings', to='prompts.promptdefinition')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prompt_ratings', to=settings.AUTH_USER_MODEL)),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings', to='prompts.promptversion')),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='PromptQualitySnapshot',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('OK', 'OK'), ('WATCH', 'Beobachten'), ('WARN', 'Warnung'), ('CRITICAL', 'Kritisch')], default='WATCH', max_length=20)),
                ('rating_count', models.PositiveIntegerField(default=0)),
                ('recent_count', models.PositiveIntegerField(default=0)),
                ('previous_count', models.PositiveIntegerField(default=0)),
                ('recent_average', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('previous_average', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('average_drop', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('calculated_at', models.DateTimeField()),
                ('definition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quality_snapshots', to='prompts.promptdefinition')),
                ('policy', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='snapshots', to='prompts.promptqualitypolicy')),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quality_snapshots', to='prompts.promptversion')),
            ],
            options={'ordering': ['-calculated_at']},
        ),
        migrations.AddConstraint(
            model_name='promptqualitypolicy',
            constraint=models.UniqueConstraint(condition=models.Q(('active', True)), fields=('active',), name='uniq_active_prompt_quality_policy'),
        ),
        migrations.AddConstraint(
            model_name='promptqualitypolicy',
            constraint=models.CheckConstraint(condition=models.Q(('minimum_average__gte', 1), ('minimum_average__lte', 5)), name='quality_min_avg_1_5'),
        ),
        migrations.AddConstraint(
            model_name='promptqualitypolicy',
            constraint=models.CheckConstraint(condition=models.Q(('critical_average__gte', 1), ('critical_average__lte', 5)), name='quality_critical_avg_1_5'),
        ),
        migrations.AddConstraint(
            model_name='prompttestcase',
            constraint=models.UniqueConstraint(fields=('version', 'name'), name='uniq_prompt_testcase_name'),
        ),
        migrations.AddConstraint(
            model_name='promptrating',
            constraint=models.UniqueConstraint(fields=('version', 'user'), name='uniq_prompt_rating_user_version'),
        ),
        migrations.AddConstraint(
            model_name='promptrating',
            constraint=models.CheckConstraint(condition=models.Q(('stars__gte', 1), ('stars__lte', 5)), name='prompt_rating_1_to_5'),
        ),
        migrations.AddIndex(
            model_name='promptrating',
            index=models.Index(fields=['definition', '-created_at'], name='prompts_rat_definit_55e584_idx'),
        ),
        migrations.AddIndex(
            model_name='promptrating',
            index=models.Index(fields=['version', '-created_at'], name='prompts_rat_version_d27fb4_idx'),
        ),
        migrations.AddIndex(
            model_name='promptqualitysnapshot',
            index=models.Index(fields=['status', '-calculated_at'], name='prompts_qua_status_245fad_idx'),
        ),
        migrations.AddIndex(
            model_name='promptqualitysnapshot',
            index=models.Index(fields=['definition', '-calculated_at'], name='prompts_qua_definit_562fcc_idx'),
        ),
    ]
