import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User, UserRole


class Command(BaseCommand):
    help = 'Create the initial PromptMaster superadmin exactly once.'

    @transaction.atomic
    def handle(self, *args, **options):
        email = os.getenv('INITIAL_ADMIN_EMAIL', '').strip().lower()
        password = os.getenv('INITIAL_ADMIN_PASSWORD', '')
        if not email or not password or password == 'CHANGE_ME':
            raise CommandError('INITIAL_ADMIN_EMAIL/PASSWORD setzen')
        if len(password) < 12:
            raise CommandError('INITIAL_ADMIN_PASSWORD muss mindestens 12 Zeichen haben')

        user = User.objects.select_for_update().filter(email=email).first()
        if user is None:
            user = User.objects.create_superuser(
                email=email,
                password=password,
                first_name=os.getenv('INITIAL_ADMIN_FIRST_NAME', 'PromptMaster').strip() or 'PromptMaster',
                last_name=os.getenv('INITIAL_ADMIN_LAST_NAME', 'Admin').strip() or 'Admin',
                two_factor_required=True,
            )
            created = True
        else:
            created = False
            # Never turn an arbitrary pre-existing customer identity into a
            # superadmin merely because the bootstrap email was misconfigured.
            if not (user.is_staff and user.is_superuser):
                raise CommandError(
                    'INITIAL_ADMIN_EMAIL gehört bereits zu einem Nicht-Superadmin. '
                    'Andere Adresse verwenden.'
                )
            dirty = []
            if not user.two_factor_required:
                user.two_factor_required = True
                dirty.append('two_factor_required')
            if not user.is_active:
                user.is_active = True
                dirty.append('is_active')
            if dirty:
                dirty.append('updated_at')
                user.save(update_fields=dirty)

        try:
            role = Role.objects.get(code='superadmin', active=True)
        except Role.DoesNotExist as exc:
            raise CommandError('Seed-Rolle superadmin fehlt; zuerst seed_defaults ausführen.') from exc
        UserRole.objects.get_or_create(user=user, role=role)
        self.stdout.write(self.style.SUCCESS('Initialer Superadmin erstellt.' if created else 'Superadmin bereits vorhanden.'))
