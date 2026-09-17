from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import PromptDefinition, PromptQualityPolicy, PromptQualitySnapshot, PromptRating, PromptVersion


def active_quality_policy():
    policy = PromptQualityPolicy.objects.filter(active=True).first()
    if policy:
        return policy

    try:
        with transaction.atomic():
            policy = PromptQualityPolicy.objects.select_for_update().filter(active=True).first()
            if policy:
                return policy
            return PromptQualityPolicy.objects.create(name='Standard', active=True)
    except IntegrityError:
        # Concurrent first access may win the partial unique constraint while
        # this transaction waits. After the savepoint rollback the committed
        # winner is the canonical policy instead of surfacing a 500.
        policy = PromptQualityPolicy.objects.filter(active=True).first()
        if policy:
            return policy
        raise


def _avg(values):
    values = [Decimal(str(v)) for v in values]
    if not values:
        return None
    return (sum(values) / Decimal(len(values))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def analyze_version(version: PromptVersion, *, persist=True):
    policy = active_quality_policy()
    rows = list(
        PromptRating.objects.filter(version=version)
        .order_by('-updated_at')
        .values_list('stars', flat=True)[: policy.recent_sample_size + policy.previous_sample_size]
    )
    recent = rows[: policy.recent_sample_size]
    previous = rows[policy.recent_sample_size : policy.recent_sample_size + policy.previous_sample_size]
    recent_average = _avg(recent)
    previous_average = _avg(previous)
    drop = None
    if recent_average is not None and previous_average is not None:
        drop = (previous_average - recent_average).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    total = PromptRating.objects.filter(version=version).count()
    if len(recent) < policy.minimum_samples:
        status = 'WATCH'
    elif recent_average is not None and recent_average <= policy.critical_average:
        status = 'CRITICAL'
    elif drop is not None and drop >= policy.critical_drop:
        status = 'CRITICAL'
    elif recent_average is not None and recent_average < policy.minimum_average:
        status = 'WARN'
    elif drop is not None and drop >= policy.warning_drop:
        status = 'WARN'
    else:
        status = 'OK'

    details = {
        'minimum_average': str(policy.minimum_average),
        'critical_average': str(policy.critical_average),
        'warning_drop': str(policy.warning_drop),
        'critical_drop': str(policy.critical_drop),
        'minimum_samples': policy.minimum_samples,
    }
    payload = {
        'definition': version.definition,
        'version': version,
        'policy': policy,
        'status': status,
        'rating_count': total,
        'recent_count': len(recent),
        'previous_count': len(previous),
        'recent_average': recent_average,
        'previous_average': previous_average,
        'average_drop': drop,
        'details': details,
        'calculated_at': timezone.now(),
    }
    if persist:
        return PromptQualitySnapshot.objects.create(**payload)
    return payload


def analyze_all_published(*, persist=True):
    results = []
    versions = PromptVersion.objects.filter(lifecycle='PUBLISHED').select_related('definition')
    for version in versions.iterator():
        results.append(analyze_version(version, persist=persist))
    return results


def quality_tasks(limit=100):
    latest_ids = []
    for definition in PromptDefinition.objects.filter(active=True).only('id'):
        snapshot = definition.quality_snapshots.order_by('-calculated_at').first()
        if snapshot:
            latest_ids.append(snapshot.id)
    return (
        PromptQualitySnapshot.objects.filter(id__in=latest_ids)
        .select_related('definition__application', 'version')
        .order_by('status', 'recent_average')[:limit]
    )


@transaction.atomic
def save_rating(*, user, version: PromptVersion, stars: int, feedback=''):
    stars = int(stars)
    if stars < 1 or stars > 5:
        raise ValueError('stars must be between 1 and 5')
    feedback = str(feedback or '').strip()[:4000] if stars <= 3 else ''
    rating, _ = PromptRating.objects.update_or_create(
        user=user,
        version=version,
        defaults={
            'definition': version.definition,
            'stars': stars,
            'feedback': feedback,
        },
    )
    rating.full_clean()
    rating.save()
    snapshot = analyze_version(version, persist=True)
    return rating, snapshot
