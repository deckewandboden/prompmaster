from apps.core.security import client_ip

from .models import AuditEvent

SENSITIVE = {'password', 'secret', 'token', 'key', 'api_key', 'authorization', 'cookie'}


def redact(value):
    if isinstance(value, dict):
        return {
            key: ('[REDACTED]' if any(part in key.lower() for part in SENSITIVE) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _actor_role(actor):
    if not getattr(actor, 'is_authenticated', False):
        return ''
    if actor.is_superuser:
        return 'superadmin'
    role = actor.role_links.select_related('role').filter(role__active=True).first()
    return role.role.code if role else ''


def audit(actor, action, obj, changes=None, request=None):
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        actor_role=_actor_role(actor),
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        ip=(client_ip(request) if request else None),
        user_agent=(request.META.get('HTTP_USER_AGENT', '')[:300] if request else ''),
        correlation_id=(getattr(request, 'correlation_id', '') if request else ''),
        changes=redact(changes or {}),
    )
