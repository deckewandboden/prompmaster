import json
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import SystemSetting
from apps.core.settings_store import set_setting
from apps.notifications.models import EmailMessage
from apps.notifications.services import get_graph_transport, get_mail_delivery
from apps.notifications.tasks import send_email_message


CONFIRM_VALUE = 'SEND-GRAPH-ACCEPTANCE'
INVALID_SENDER = '00000000-0000-0000-0000-000000000000'


def _provider_http_status(exc):
    pending = [exc]
    seen = set()
    while pending:
        candidate = pending.pop(0)
        if candidate is None or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        response = getattr(candidate, 'response', None)
        status = getattr(response, 'status_code', None)
        if status:
            return status
        pending.extend(
            [
                getattr(candidate, 'exc', None),
                getattr(candidate, 'original', None),
                getattr(candidate, '__cause__', None),
            ]
        )
    return None


class Command(BaseCommand):
    help = 'Run a real Microsoft Graph mail acceptance probe through the production EmailMessage task path.'

    def add_arguments(self, parser):
        parser.add_argument('--recipient', required=True)
        parser.add_argument('--confirm', required=True)

    def handle(self, *args, **options):
        if options['confirm'] != CONFIRM_VALUE:
            raise CommandError(
                f'Refusing external send. Pass --confirm {CONFIRM_VALUE} explicitly.'
            )

        graph = get_graph_transport()
        required = {
            'GRAPH_TENANT_ID': graph['tenant_id'],
            'GRAPH_CLIENT_ID': graph['client_id'],
            'GRAPH_CLIENT_SECRET': graph['client_secret'],
            'GRAPH_SENDER': graph['sender'],
        }
        missing = sorted(name for name, value in required.items() if not value)
        if missing:
            raise CommandError('Missing Graph configuration: ' + ', '.join(missing))
        if get_mail_delivery()['primary'] != 'graph':
            raise CommandError('Primary mail provider must be Microsoft Graph for this gate.')

        recipient = options['recipient'].strip().lower()
        if '@' not in recipient:
            raise CommandError('Recipient must be a valid e-mail address.')

        probe_id = uuid.uuid4().hex
        success = EmailMessage.objects.create(
            recipient=recipient,
            subject=f'PROMPTFINISHER Graph Acceptance {probe_id}',
            context={},
        )
        result = send_email_message.run(str(success.id))
        success.refresh_from_db()
        if result != 'sent' or success.status != 'sent':
            raise CommandError(
                f'Graph success probe did not complete the production mail task: '
                f'result={result!r}, status={success.status!r}.'
            )

        original_sender = graph['sender']
        graph_setting = SystemSetting.objects.filter(key='mail_graph').first()
        original_graph_value = graph_setting.value if graph_setting else None
        original_graph_description = graph_setting.description if graph_setting else ''
        delivery_setting = SystemSetting.objects.filter(key='mail_delivery').first()
        original_delivery_value = delivery_setting.value if delivery_setting else None
        original_delivery_description = delivery_setting.description if delivery_setting else ''
        failure = EmailMessage.objects.create(
            recipient=recipient,
            subject=f'PROMPTFINISHER Graph Failure Probe {probe_id}',
            context={},
        )
        failure_exc = None
        try:
            set_setting(
                'mail_delivery',
                {
                    'mode': 'manual',
                    'primary': 'graph',
                    'fallback_1': '',
                    'fallback_2': '',
                },
                'Temporary Graph acceptance routing probe',
            )
            set_setting(
                'mail_graph',
                {
                    'tenant_id': graph['tenant_id'],
                    'client_id': graph['client_id'],
                    'sender': INVALID_SENDER,
                },
                'Temporary Graph acceptance failure probe',
            )
            try:
                send_email_message.run(str(failure.id))
            except Exception as exc:
                failure_exc = exc
            else:
                raise CommandError(
                    'Graph failure probe unexpectedly succeeded with an invalid sender.'
                )
        finally:
            if original_graph_value is None:
                SystemSetting.objects.filter(key='mail_graph').delete()
            else:
                set_setting(
                    'mail_graph',
                    original_graph_value,
                    original_graph_description,
                )
            if original_delivery_value is None:
                SystemSetting.objects.filter(key='mail_delivery').delete()
            else:
                set_setting(
                    'mail_delivery',
                    original_delivery_value,
                    original_delivery_description,
                )

        failure.refresh_from_db()
        failure_status = _provider_http_status(failure_exc)
        if not failure_status or failure_status < 400:
            raise CommandError('Graph failure probe did not produce a real provider HTTP error.')
        if failure.status != 'failed' or failure.retry_count < 1:
            raise CommandError(
                'Graph provider failure did not traverse the production failed/retry state path.'
            )

        self.stdout.write(
            json.dumps(
                {
                    'status': 'ok',
                    'probe_id': probe_id,
                    'recipient': recipient,
                    'sender': original_sender,
                    'request_id': success.provider_reference,
                    'success_message_id': str(success.id),
                    'failure_message_id': str(failure.id),
                    'provider_failure_status': failure_status,
                    'retry_count': failure.retry_count,
                    'retry_path': 'production EmailMessage/Celery task path exercised with real Graph provider failure',
                },
                sort_keys=True,
            )
        )
