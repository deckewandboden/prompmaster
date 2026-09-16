from django.db import migrations


def normalize_chargeback_status(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    MollieEvent = apps.get_model('payments', 'MollieEvent')
    Payment.objects.filter(status='charged_back').update(status='chargeback')
    MollieEvent.objects.filter(provider_status='charged_back').update(provider_status='chargeback')


def restore_legacy_chargeback_status(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    MollieEvent = apps.get_model('payments', 'MollieEvent')
    Payment.objects.filter(status='chargeback').update(status='charged_back')
    MollieEvent.objects.filter(provider_status='chargeback').update(provider_status='charged_back')


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            normalize_chargeback_status,
            reverse_code=restore_legacy_chargeback_status,
        ),
    ]
