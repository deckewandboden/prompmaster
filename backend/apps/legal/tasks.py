from datetime import timedelta

from celery import shared_task
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.companies.models import Invitation
from apps.devices.models import DeviceRegistration
from apps.notifications.models import EmailMessage
from apps.ops.models import SystemAlert, TaskFailure

from .models import RetentionPolicy


BATCH_SIZE = 2000


def _delete_in_batches(queryset):
    total = 0
    while True:
        ids = list(queryset.values_list('pk', flat=True)[:BATCH_SIZE])
        if not ids:
            return total
        deleted, _ = queryset.model.objects.filter(pk__in=ids).delete()
        total += deleted


def _cutoff(policy):
    return timezone.now() - timedelta(days=policy.retain_days)


def _expired_invitations(policy):
    # Invitation expiry is authoritative. retain_days is the grace period after
    # the invitation became unusable, irrespective of whether it was accepted,
    # revoked, or simply expired unused.
    cutoff = _cutoff(policy)
    qs = Invitation.objects.filter(expires_at__lt=cutoff)
    return _delete_in_batches(qs.order_by('pk'))


def _email_messages(policy):
    return _delete_in_batches(EmailMessage.objects.filter(created_at__lt=_cutoff(policy)).order_by('pk'))


def _revoked_devices(policy):
    return _delete_in_batches(DeviceRegistration.objects.filter(revoked_at__lt=_cutoff(policy)).order_by('pk'))


def _resolved_alerts(policy):
    return _delete_in_batches(SystemAlert.objects.filter(resolved_at__lt=_cutoff(policy)).order_by('pk'))


def _resolved_task_failures(policy):
    return _delete_in_batches(TaskFailure.objects.filter(resolved_at__lt=_cutoff(policy)).order_by('pk'))


def _expired_sessions(policy):
    # Session expiry itself remains authoritative; retain_days adds a grace
    # period after expiry when explicitly requested by policy.
    cutoff = _cutoff(policy)
    return _delete_in_batches(Session.objects.filter(expire_date__lt=cutoff).order_by('pk'))


HANDLERS = {
    'expired_invitations': _expired_invitations,
    'email_messages': _email_messages,
    'revoked_devices': _revoked_devices,
    'resolved_system_alerts': _resolved_alerts,
    'resolved_task_failures': _resolved_task_failures,
    'expired_sessions': _expired_sessions,
}


@shared_task
def apply_retention():
    result = {}
    for policy in RetentionPolicy.objects.filter(active=True).order_by('data_class'):
        handler = HANDLERS.get(policy.data_class)
        if handler is None:
            # Unknown/legally sensitive classes are deliberately never deleted
            # by a generic fallback.
            result[policy.data_class] = {'status': 'unsupported', 'deleted': 0}
            continue
        result[policy.data_class] = {'status': 'ok', 'deleted': handler(policy)}
    return result
