from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Company(TimeStampedModel):
    STATUS = [('active', 'Aktiv'), ('inactive', 'Inaktiv')]

    customer_number = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=200)
    legal_form = models.CharField(max_length=80, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=60, blank=True)
    street = models.CharField(max_length=160, blank=True)
    house_number = models.CharField(max_length=40, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=2, default='DE')
    vat_id = models.CharField(max_length=40, blank=True)
    tax_number = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='active')

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['status', 'country']),
        ]

    def __str__(self):
        return self.name


class Membership(TimeStampedModel):
    ROLE = [('admin', 'Firmenadministrator'), ('member', 'Mitarbeiter')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE, default='member')
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'user'],
                condition=Q(active=True),
                name='uniq_active_company_user',
            ),
            models.UniqueConstraint(
                fields=['company'],
                condition=Q(active=True, role='admin'),
                name='uniq_active_company_admin',
            ),
            # V1 has no company switcher. One active company context per identity
            # prevents ambiguous tenant scoping in every portal request.
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(active=True),
                name='uniq_active_company_membership_per_user',
            ),
        ]
        indexes = [models.Index(fields=['company', 'active', 'role'])]

    def __str__(self):
        return f'{self.company} · {self.user} · {self.role}'


class Invitation(TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sent_invitations',
    )

    class Meta:
        indexes = [models.Index(fields=['company', 'email', 'expires_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'email'],
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name='uniq_open_company_invite',
            )
        ]

    def is_valid(self):
        from django.utils import timezone

        return not self.accepted_at and not self.revoked_at and self.expires_at > timezone.now()

    def __str__(self):
        return f'{self.email} → {self.company}'


class PrivateCustomerProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='private_customer',
    )
    customer_number = models.CharField(max_length=30, unique=True)
    street = models.CharField(max_length=160, blank=True)
    house_number = models.CharField(max_length=40, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=2, default='DE')

    def __str__(self):
        return self.customer_number
