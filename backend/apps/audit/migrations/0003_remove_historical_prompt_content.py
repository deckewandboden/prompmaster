from django.db import migrations


def remove_content(apps, schema_editor):
    # A one-time privacy repair using the historical model. Runtime audit
    # events remain append-only; identities, actions and timestamps survive.
    Event = apps.get_model('audit', 'AuditEvent')
    allowed = {'ok', 'mode', 'task_id', 'version', 'total', 'passed', 'failed', 'service_account'}
    for event in Event.objects.using(schema_editor.connection.alias).filter(action='mcp.prompt.test').iterator():
        metadata = {key: value for key, value in event.changes.items() if key in allowed}
        if metadata != event.changes:
            Event.objects.using(schema_editor.connection.alias).filter(pk=event.pk).update(changes=metadata)


class Migration(migrations.Migration):
    dependencies = [('audit', '0002_rename_audit_a_action_idx_audit_audit_action_0c0ad1_idx_and_more')]
    operations = [migrations.RunPython(remove_content, migrations.RunPython.noop)]
