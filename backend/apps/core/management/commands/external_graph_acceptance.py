import json
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.models import EmailMessage
from apps.notifications.tasks import send_email_message


CONFIRM_VALUE = 'SEND-GRAPH-ACCEPTANCE'
INVALID_SENDER = '00000000-0000-0000-0000-000000000000'


def _provider_http_status(exc):
    candidates = [exc, getattr(exc, 'exc', None)]
    for candidate in candidates:
        response = getattr(candidate, 'response', None) if candidate is not None else None
        status = getattr(response, 'status_code', None)
        if status:
            return status
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

        required = {
            'GRAPH_TENANT_ID': settings.GRAPH_TENANT_ID,
            'GRAPH_CLIENT_ID': settings.GRAPH_CLIENT_ID,
            'GRAPH_CLIENT_SECRET': settings.GRAPH_CLIENT_SECRET,
            'GRAPH_SENDER': settings.GRAPH_SENDER,
        }
        missing = sorted(name for name, value in required.items() if not value)
        if missing:
            raise CommandError('Missing Graph configuration: ' + ', '.join(missing))
        if settings.EMAIL_PROVIDER.lower().strip() not in {'graph', 'microsoft_graph'}:
            raise CommandError('EMAIL_PROVIDER must be graph or microsoft_graph for this gate.')

        recipient = options['recipient'].strip().lower()
        if '@' not in recipient:
            raise CommandError('Recipient must be a valid e-mail address.')

        probe_id = uuid.uuid4().hex
        success = EmailMessage.objects.create(
            recipient=recipient,
            subject=f'PromptMaster Graph Acceptance {probe_id}',
            context={},
        )
        result = send_email_message.run(str(success.id))
        success.refresh_from_db()
        if result != 'sent' or success.status != 'sent':
            raise CommandError(
                f'Graph success probe did not complete the production mail task: '
                f'result={result!r}, status={success.status!r}.'
            )

        original_sender = settings.GRAPH_SENDER
        failure = EmailMessage.objects.create(
            recipient=recipient,
            subject=f'PromptMaster Graph Failure Probe {probe_id}',
            context={},
        )
        failure_exc = None
        try:
            settings.GRAPH_SENDER = INVALID_SENDER
            try:
                send_email_message.run(str(failure.id))
            except Exception as exc:
                failure_exc = exc
            else:
                raise CommandError(
                    'Graph failure probe unexpectedly succeeded with an invalid sender.'
                )
        finally:
            settings.GRAPH_SENDER = original_sender

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
