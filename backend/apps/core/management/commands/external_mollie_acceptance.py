import ipaddress
import json
from decimal import Decimal
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from django.test import Client
from django.utils import timezone

from apps.companies.models import Membership
from apps.payments.mollie import MollieClient
from apps.payments.models import MollieEvent, Payment
from apps.payments.services import create_refund_request, submit_refund


START_CONFIRM = 'CREATE-MOLLIE-TEST-PAYMENT'
REFUND_CONFIRM = 'CREATE-MOLLIE-TEST-REFUND'


class Command(BaseCommand):
    help = 'Run staged acceptance against Mollie test mode using PromptMaster production code paths.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['start', 'verify', 'refund'])
        parser.add_argument('--user-email')
        parser.add_argument('--payment-id')
        parser.add_argument('--base-url')
        parser.add_argument('--expect', choices=[
            'created', 'open', 'pending', 'authorized', 'paid', 'failed',
            'canceled', 'expired', 'refunded_partial', 'refunded_full',
            'chargeback', 'chargeback_reversed',
        ])
        parser.add_argument('--confirm')

    def _client(self):
        client = MollieClient()
        if not client.key:
            raise CommandError('MOLLIE_API_KEY is not configured.')
        if not client.key.startswith('test_'):
            raise CommandError('External Mollie acceptance refuses non-test API keys.')
        return client

    def handle(self, *args, **options):
        client = self._client()
        action = options['action']
        if action == 'start':
            return self._start(client, options)
        if action == 'verify':
            return self._verify(client, options)
        return self._refund(options)

    def _base_url(self, options):
        raw = (options.get('base_url') or '').strip()
        if not raw and settings.CADDY_DOMAIN:
            raw = f'https://{settings.CADDY_DOMAIN}'
        parsed = urlsplit(raw)
        if parsed.scheme != 'https' or not parsed.netloc:
            raise CommandError('Use an explicit HTTPS --base-url or configure CADDY_DOMAIN.')
        hostname = (parsed.hostname or '').strip().lower().rstrip('.')
        if (
            not hostname
            or hostname == 'localhost'
            or hostname.endswith(('.localhost', '.local', '.invalid', '.test'))
        ):
            raise CommandError('Mollie acceptance requires a publicly reachable HTTPS hostname.')
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None
        if ip is not None and (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise CommandError('Mollie acceptance refuses non-public IP addresses.')
        return parsed

    def _start(self, client, options):
        if options.get('confirm') != START_CONFIRM:
            raise CommandError(
                f'Refusing provider-side payment creation. Pass --confirm {START_CONFIRM}.'
            )
        email = (options.get('user_email') or '').strip().lower()
        if not email:
            raise CommandError('--user-email is required for start.')
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            raise CommandError('Acceptance user does not exist or is inactive.')
        if not user.email_verified_at:
            raise CommandError('Acceptance user must have a verified e-mail address.')

        parsed = self._base_url(options)
        host = parsed.netloc
        started = timezone.now()

        client_http = Client()
        client_http.force_login(user)
        session = client_http.session
        now_ts = timezone.now().timestamp()
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now_ts
        session['last_activity_at'] = now_ts
        session.save()

        payload = {
            'quantity': '1',
            'accept_terms': 'on',
            'accept_privacy': 'on',
        }
        if not user.company_memberships.filter(active=True).exists():
            if not hasattr(user, 'private_customer'):
                raise CommandError('Private acceptance user has no PrivateCustomerProfile.')
            payload['accept_withdrawal'] = 'on'

        response = client_http.post(
            '/portal/licenses/buy/',
            payload,
            secure=True,
            HTTP_HOST=host,
            follow=False,
        )
        location = response.headers.get('Location', '')
        if response.status_code != 302 or not location.startswith('https://'):
            body = response.content.decode('utf-8', errors='replace')
            raise CommandError(
                f'Portal checkout did not redirect to Mollie (HTTP {response.status_code}). '
                f'Form/provider response: {body[:500]}'
            )

        payment_qs = Payment.objects.filter(created_at__gte=started).select_related('order')
        membership = user.company_memberships.filter(active=True).select_related('company').first()
        if membership:
            payment_qs = payment_qs.filter(order__company=membership.company)
        else:
            payment_qs = payment_qs.filter(order__private_user=user)
        payment = payment_qs.order_by('-created_at').first()
        if not payment:
            raise CommandError('Checkout redirected but no local Payment row was created.')

        provider = client.get_payment(payment.provider_payment_id)
        change_state = (
            ((provider.get('_links') or {}).get('changePaymentState') or {}).get('href') or ''
        )
        self.stdout.write(json.dumps({
            'status': 'started',
            'order': payment.order.order_number,
            'payment_id': payment.provider_payment_id,
            'checkout_url': location,
            'provider_status': provider.get('status'),
            'change_payment_state_url': change_state,
            'webhook_url': (
                ((provider.get('_links') or {}).get('webhook') or {}).get('href') or
                f'{parsed.scheme}://{parsed.netloc}/api/webhooks/mollie/'
            ),
            'next': 'Complete the hosted Mollie test checkout, then run verify --expect paid.',
        }, sort_keys=True))

    def _payment(self, options):
        payment_id = (options.get('payment_id') or '').strip()
        if not payment_id:
            raise CommandError('--payment-id is required.')
        try:
            return Payment.objects.select_related('order').get(provider_payment_id=payment_id)
        except Payment.DoesNotExist as exc:
            raise CommandError('No local PromptMaster payment exists for this Mollie ID.') from exc

    def _assert_provider_state(self, payment, provider, expected):
        """Require the live Mollie payload to agree with the expected local state."""
        if not expected:
            return

        provider_status = str(provider.get('status') or '').strip().lower()
        status_map = {
            'created': 'created',
            'open': 'open',
            'pending': 'pending',
            'authorized': 'authorized',
            'failed': 'failed',
            'canceled': 'canceled',
            'expired': 'expired',
            'charged_back': 'chargeback',
        }

        if provider_status == 'paid':
            refunded_data = provider.get('amountRefunded') or {}
            raw_refunded = refunded_data.get('value')
            try:
                refunded_amount = (
                    Decimal(str(raw_refunded)).quantize(Decimal('0.01'))
                    if raw_refunded not in (None, '')
                    else Decimal('0.00')
                )
            except Exception as exc:
                raise CommandError('Mollie returned an invalid refunded amount.') from exc

            if refunded_amount > 0:
                provider_state = (
                    'refunded_full'
                    if refunded_amount >= payment.amount.quantize(Decimal('0.01'))
                    else 'refunded_partial'
                )
                if expected in {'refunded_partial', 'refunded_full'}:
                    local_refunded = (
                        payment.refunds.filter(status='succeeded')
                        .aggregate(total=Sum('amount'))['total']
                        or Decimal('0.00')
                    ).quantize(Decimal('0.01'))
                    if local_refunded != refunded_amount:
                        raise CommandError(
                            'Live Mollie refunded amount does not match the sum of locally '
                            'succeeded refunds.'
                        )
            elif expected == 'chargeback_reversed':
                # Mollie returns a recovered chargeback as paid again. The
                # exact chargeback_reversed transition must additionally be
                # evidenced by a processed local event in _verify().
                provider_state = 'chargeback_reversed'
            else:
                provider_state = 'paid'
        else:
            provider_state = status_map.get(provider_status, 'unknown')

        if provider_state != expected:
            raise CommandError(
                f'Live Mollie state resolves to {provider_state!r}, expected {expected!r}. '
                'The provider and local webhook state are not yet aligned.'
            )

    def _assert_business_state(self, payment, expected):
        """Fail closed when provider status is ahead of local business finalization."""
        if not expected:
            return

        payment.refresh_from_db()
        order = payment.order
        order.refresh_from_db()

        if expected == 'paid':
            if payment.status != 'paid' or order.status != 'paid' or not payment.processed_paid:
                raise CommandError(
                    'Paid acceptance requires Payment=paid, Order=paid and processed_paid=true.'
                )
            if not order.items.filter(license_terms__status='active').exists():
                raise CommandError(
                    'Paid acceptance has no active LicenseTerm created through the real activation path.'
                )
            return

        if expected in {'refunded_partial', 'refunded_full'}:
            if order.status != 'paid':
                raise CommandError('Refund acceptance requires the paid order to remain terminal.')
            succeeded = payment.refunds.filter(status='succeeded').select_related('term__license')
            if not succeeded.exists():
                raise CommandError(
                    'Payment reports a refund state but no local Refund was reconciled to succeeded.'
                )
            if succeeded.exclude(term__status='refunded').exists():
                raise CommandError(
                    'A succeeded refund still has a LicenseTerm that was not finalized as refunded.'
                )
            if payment.refunds.filter(status__in=['created', 'submitted']).exists():
                raise CommandError(
                    'Refund acceptance still has an unfinished local refund request.'
                )
            refunded_total = succeeded.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            if expected == 'refunded_full' and refunded_total < payment.amount:
                raise CommandError(
                    'Payment is refunded_full but locally succeeded refunds do not cover the payment amount.'
                )
            if expected == 'refunded_partial' and not (
                Decimal('0.00') < refunded_total < payment.amount
            ):
                raise CommandError(
                    'Payment is refunded_partial but the locally succeeded refund total is not partial.'
                )
            return

        if expected in {'chargeback', 'chargeback_reversed'}:
            if order.status != 'paid':
                raise CommandError('Chargeback acceptance requires the original order to remain paid.')
            from apps.licenses.models import License

            licenses = License.objects.filter(
                terms__order_item__order=order,
                terms__status='active',
            ).distinct()
            if not licenses.exists():
                raise CommandError(
                    'Chargeback acceptance found no active license term linked to the paid order.'
                )
            if expected == 'chargeback':
                if licenses.exclude(status='payment_review').exists():
                    raise CommandError(
                        'Chargeback payment state is present but not every affected license is in payment_review.'
                    )
            elif licenses.filter(status='payment_review').exists():
                raise CommandError(
                    'Chargeback reversal is present but an affected license is still in payment_review.'
                )
            return

        if expected in {'failed', 'canceled', 'expired'}:
            wanted = 'canceled' if expected == 'canceled' else 'failed'
            if order.status != wanted:
                raise CommandError(
                    f'Payment is {expected!r} but order status is {order.status!r}, expected {wanted!r}.'
                )

    def _verify(self, client, options):
        payment = self._payment(options)
        provider = client.get_payment(payment.provider_payment_id)
        payment.refresh_from_db()
        expected = options.get('expect')
        if expected and payment.status != expected:
            raise CommandError(
                f'Local payment status is {payment.status!r}, expected {expected!r}. '
                'Wait for/retry the real Mollie webhook before accepting the gate.'
            )
        processed_events = MollieEvent.objects.filter(
            payment=payment,
            processed_at__isnull=False,
        ).count()
        if expected and expected not in {'created', 'open', 'pending'}:
            expected_events = MollieEvent.objects.filter(
                payment=payment,
                provider_status=expected,
                processed_at__isnull=False,
            ).count()
            if expected_events < 1:
                raise CommandError(
                    f'No processed Mollie webhook event exists for expected state {expected!r}.'
                )

        self._assert_provider_state(payment, provider, expected)
        self._assert_business_state(payment, expected)

        change_state = (
            ((provider.get('_links') or {}).get('changePaymentState') or {}).get('href') or ''
        )
        self.stdout.write(json.dumps({
            'status': 'ok',
            'payment_id': payment.provider_payment_id,
            'order': payment.order.order_number,
            'local_status': payment.status,
            'provider_status': provider.get('status'),
            'processed_webhook_events': processed_events,
            'change_payment_state_url': change_state,
        }, sort_keys=True))

    def _refund(self, options):
        if options.get('confirm') != REFUND_CONFIRM:
            raise CommandError(
                f'Refusing provider-side refund. Pass --confirm {REFUND_CONFIRM}.'
            )
        payment = self._payment(options)
        if payment.status not in {'paid', 'chargeback_reversed', 'refunded_partial'}:
            raise CommandError(f'Payment state {payment.status!r} is not refundable.')

        term = (
            payment.order.items.filter(license_terms__status='active')
            .values_list('license_terms__id', flat=True)
            .order_by('-license_terms__valid_until')
            .first()
        )
        if not term:
            raise CommandError('Paid acceptance order has no active LicenseTerm to refund.')
        from apps.licenses.models import LicenseTerm
        term = LicenseTerm.objects.select_related('license').get(pk=term)

        actor = payment.order.private_user
        if actor is None and payment.order.company_id:
            admin = (
                Membership.objects.filter(
                    company_id=payment.order.company_id,
                    role='admin',
                    active=True,
                )
                .select_related('user')
                .first()
            )
            actor = admin.user if admin else None

        refund = create_refund_request(
            term=term,
            actor=actor,
            reason='PromptMaster external Mollie acceptance',
        )
        refund = submit_refund(refund)
        self.stdout.write(json.dumps({
            'status': refund.status,
            'payment_id': payment.provider_payment_id,
            'refund_id': refund.provider_refund_id,
            'amount': str(refund.amount),
            'remaining_days': refund.remaining_days,
            'next': 'Run verify again after Mollie has delivered the refund webhook/state update.',
        }, sort_keys=True))
