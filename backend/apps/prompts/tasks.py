from celery import shared_task

from .quality import analyze_all_published


@shared_task(name='apps.prompts.tasks.refresh_prompt_quality')
def refresh_prompt_quality():
    snapshots = analyze_all_published(persist=True)
    return {'snapshots': len(snapshots)}
