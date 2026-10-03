from django.db import migrations


def ensure_support_reply_template(apps, schema_editor):
    EmailTemplate = apps.get_model('notifications', 'EmailTemplate')
    EmailTemplate.objects.get_or_create(
        code='support_reply',
        defaults={
            'subject': 'PROMPTFINISHER: {subject}',
            'body_text': (
                'Guten Tag,\n\n'
                'wir haben auf Ihre PROMPTFINISHER-Anfrage „{subject}“ geantwortet:\n\n'
                '{message}\n\n'
                'Vorgang: {reference}\n\n'
                'Viele Grüße\nIhr PROMPTFINISHER-Support'
            ),
            'active': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('support', '0003_supportmessage'),
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(ensure_support_reply_template, migrations.RunPython.noop),
    ]
