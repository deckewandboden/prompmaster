from django.db import migrations, models


def forwards(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Payment.objects.filter(status='charged_back').update(status='chargeback')
    Payment.objects.filter(
        status__in=['failed', 'canceled', 'expired'],
        failed_at__isnull=True,
    ).update(failed_at=models.F('updated_at'))


def backwards(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Payment.objects.filter(status='chargeback').update(status='charged_back')


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='failed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='payment',
            name='status',
            field=models.CharField(
                choices=[
                    ('created', 'Erstellt'),
                    ('open', 'Offen'),
                    ('pending', 'Ausstehend'),
                    ('authorized', 'Autorisiert'),
                    ('paid', 'Bezahlt'),
                    ('failed', 'Fehlgeschlagen'),
                    ('canceled', 'Storniert'),
                    ('expired', 'Abgelaufen'),
                    ('refunded_partial', 'Teilweise erstattet'),
                    ('refunded_full', 'Vollständig erstattet'),
                    ('chargeback', 'Chargeback'),
                    ('chargeback_reversed', 'Chargeback zurückgenommen'),
                    ('unknown', 'Unbekannt'),
                ],
                max_length=40,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
