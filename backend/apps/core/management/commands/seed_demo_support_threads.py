from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.support.models import SupportMessage, SupportRequest

from .seed_demo_data import COMPANY_SUPPORT_DEMOS, PRIVATE_SUPPORT_DEMOS


class Command(BaseCommand):
    help = (
        'Aktualisiert ausschließlich vorhandene [DEMO]-Supportanfragen und '
        'deren Nachrichtenverläufe. Andere Demo-Daten bleiben unverändert.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--allow-production-presentation',
            action='store_true',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'production' and not options['allow_production_presentation']:
            raise CommandError(
                'In Production ist --allow-production-presentation erforderlich.'
            )

        staff = {
            1: User.objects.filter(
                email='demo.support1@promptmaster.invalid',
                is_staff=True,
            ).first(),
            2: User.objects.filter(
                email='demo.support2@promptmaster.invalid',
                is_staff=True,
            ).first(),
        }

        updated = 0
        messages = 0

        for index in range(1, 6):
            subject = f'[DEMO] DEMO-{1000 + index} – Beispielanfrage'
            support = SupportRequest.objects.filter(subject=subject).select_related('user').first()
            if support is None:
                raise CommandError(f'Demo-Supportfall fehlt: {subject}')
            messages += self._apply(
                support,
                support.user,
                COMPANY_SUPPORT_DEMOS[index],
                staff,
            )
            updated += 1

        for index in range(1, 4):
            subject = f'[DEMO] DEMO-P-{2000 + index} – Privatanfrage'
            support = SupportRequest.objects.filter(subject=subject).select_related('user').first()
            if support is None:
                raise CommandError(f'Demo-Supportfall fehlt: {subject}')
            messages += self._apply(
                support,
                support.user,
                PRIVATE_SUPPORT_DEMOS[index],
                staff,
            )
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Demo-Supportverläufe aktualisiert: '
                f'{updated} Vorgänge / {messages} Verlaufsnachrichten.'
            )
        )
        self.stdout.write('Benutzer und Zugangsdaten: UNVERÄNDERT.')

    def _apply(self, support, customer, spec, staff):
        if not support.subject.startswith('[DEMO]'):
            raise CommandError('Nur [DEMO]-Supportfälle dürfen verändert werden.')

        support.message = spec['message']
        support.status = spec['status']
        support.save(update_fields=['message', 'status', 'updated_at'])
        support.messages.all().delete()

        count = 0
        for offset_hours, sender_type, visibility, staff_slot, body in spec['thread']:
            author = customer if sender_type == 'customer' else staff.get(staff_slot)
            item = SupportMessage.objects.create(
                support_request=support,
                author_user=author,
                sender_type=sender_type,
                visibility=visibility,
                body=body,
            )
            occurred_at = support.created_at + timedelta(hours=offset_hours)
            SupportMessage.objects.filter(pk=item.pk).update(
                created_at=occurred_at,
                updated_at=occurred_at,
            )
            count += 1
        return count
