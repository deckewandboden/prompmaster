import json
import uuid
from types import SimpleNamespace

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services import _send_graph


CONFIRM_VALUE = 'SEND-GRAPH-ACCEPTANCE'
INVALID_SENDER = '00000000-0000-0000-0000-000000000000'


class Command(BaseCommand):
    help = 'Run a real Microsoft Graph mail acceptance probe without persisting secrets.'

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
        message = SimpleNamespace(
            subject=f'PromptMaster Graph Acceptance {probe_id}',
            recipient=recipient,
        )
        request_id = _send_graph(
            message,
            'PromptMaster external Graph acceptance. '
            f'Probe ID: {probe_id}. No action is required.',
        )

        original_sender = settings.GRAPH_SENDER
        failure_status = None
        try:
            settings.GRAPH_SENDER = INVALID_SENDER
            try:
                _send_graph(
                    SimpleNamespace(
                        subject=f'PromptMaster Graph Failure Probe {probe_id}',
                        recipient=recipient,
                    ),
                    'This message must not be delivered because the sender is intentionally invalid.',
                )
            except requests.HTTPError as exc:
                failure_status = exc.response.status_code if exc.response is not None else None
            else:
                raise CommandError(
                    'Graph failure probe unexpectedly succeeded with an invalid sender.'
                )
        finally:
            settings.GRAPH_SENDER = original_sender

        if not failure_status or failure_status < 400:
            raise CommandError('Graph failure probe did not produce a provider error.')

        self.stdout.write(
            json.dumps(
                {
                    'status': 'ok',
                    'probe_id': probe_id,
                    'recipient': recipient,
                    'sender': original_sender,
                    'request_id': request_id,
                    'provider_failure_status': failure_status,
                    'retry_path': 'covered by apps.notifications.tasks.send_email_message CI regression',
                },
                sort_keys=True,
            )
        )
