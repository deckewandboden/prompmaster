from django.apps import AppConfig


class OpsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ops'

    def ready(self):
        from celery.signals import task_failure
        from django.utils import timezone

        from .models import TaskFailure

        @task_failure.connect(weak=False)
        def _record_task_failure(sender=None, task_id=None, exception=None, **kwargs):
            if not task_id:
                return
            TaskFailure.objects.update_or_create(
                task_id=str(task_id)[:100],
                defaults={
                    'task_name': str(getattr(sender, 'name', sender) or 'unknown')[:200],
                    'error': str(exception or 'unknown error')[:1000],
                    'failed_at': timezone.now(),
                    'resolved_at': None,
                },
            )
