import uuid

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_payment_failed_at_and_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefundAttempt',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('number', models.PositiveIntegerField()),
                ('idempotency_key', models.CharField(max_length=180, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('provider_refund_id', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                ('status', models.CharField(choices=[('submitted', 'Übermittelt'), ('ambiguous', 'Ausgang unklar'), ('succeeded', 'Erfolgreich'), ('failed', 'Fehlgeschlagen')], default='submitted', max_length=30)),
                ('error_class', models.CharField(blank=True, max_length=120)),
                ('submitted_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('refund', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attempts', to='payments.refund')),
            ],
        ),
        migrations.AddConstraint(
            model_name='refundattempt',
            constraint=models.UniqueConstraint(fields=('refund', 'number'), name='uniq_refund_attempt_number'),
        ),
        migrations.AddIndex(
            model_name='refundattempt',
            index=models.Index(fields=['refund', '-number'], name='payments_re_refund__a900d6_idx'),
        ),
        migrations.AddIndex(
            model_name='refundattempt',
            index=models.Index(fields=['status', 'submitted_at'], name='payments_re_status_5849ef_idx'),
        ),
    ]
