from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.devices.services import validate_device_token
from apps.proaccess.services import active_product_assignment

from .composer_core import PromptValidationError
from .services import build_spec, catalog_snapshot, compose_task, published_version, task_entitled
from .quality import save_rating

DEVICE_COOKIE = 'pm_device'


def _error(exc: PromptValidationError, status: int = 400):
    return JsonResponse(
        {'ok': False, 'error': {'code': exc.code, 'field': exc.field, 'message': str(exc)}},
        status=status,
    )


def _require_pro_access(request):
    if not request.user.is_authenticated:
        raise PromptValidationError('Anmeldung erforderlich.', code='authentication_required')
    assignment = active_product_assignment(request.user, 'PRO')
    if not assignment:
        raise PromptValidationError('Aktive PromptMaster-Pro-Lizenz erforderlich.', code='license_required')
    device = validate_device_token(
        request.user,
        request.COOKIES.get(DEVICE_COOKIE, ''),
        product_code='PRO',
    )
    if not device or device.license_id != assignment.license_id:
        raise PromptValidationError('Registriertes Gerät erforderlich.', code='device_required')


@require_GET
def catalog(request):
    product = (request.GET.get('product') or 'PRO').upper()
    if product == 'PRO':
        try:
            _require_pro_access(request)
        except PromptValidationError as exc:
            return _error(exc, 403 if exc.code != 'authentication_required' else 401)
    elif product != 'FREE':
        return _error(PromptValidationError('Unbekanntes Produkt.', field='product', code='choice'))
    response = JsonResponse({'ok': True, 'catalog': catalog_snapshot(product)})
    response['Cache-Control'] = 'no-store'
    return response




def _public_spec(spec):
    return {
        'task_id': spec['task_id'],
        'application': spec['application'],
        'version': spec['version'],
        'policy': {
            'version': spec['policy']['version'],
            'source_labels': spec['policy']['source_labels'],
            'tone_rules': spec['policy']['tone_rules'],
            'detail_rules': spec['policy']['detail_rules'],
        },
    }


@require_GET
def task_detail(request, task_id):
    product = (request.GET.get('product') or 'PRO').upper()
    if product == 'PRO':
        try:
            _require_pro_access(request)
        except PromptValidationError as exc:
            return _error(exc, 403 if exc.code != 'authentication_required' else 401)
    elif product != 'FREE':
        return _error(PromptValidationError('Unbekanntes Produkt.', field='product', code='choice'))
    try:
        if not task_entitled(product, task_id):
            raise PromptValidationError(
                'Diese Prompt-Aufgabe ist für das ausgewählte PromptMaster-Produkt nicht freigeschaltet.',
                field='task_id',
                code='entitlement_required',
            )
        spec = build_spec(task_id)
    except PromptValidationError as exc:
        status = 404 if exc.code == 'not_found' else 403 if exc.code == 'entitlement_required' else 400
        return _error(exc, status)
    response = JsonResponse({'ok': True, 'prompt': _public_spec(spec)})
    response['Cache-Control'] = 'no-store'
    return response


@require_POST
def compose(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(PromptValidationError('Ungültiges JSON.', code='invalid_json'))

    product = str(body.get('product') or 'PRO').upper()
    if product != 'PRO':
        # Free remains the unchanged standalone Golden Master until its 16
        # legacy task contracts have an explicitly reviewed PM20 mapping.
        return _error(
            PromptValidationError(
                'Serverseitige Free-Komposition ist bis zum geprüften Legacy-Mapping deaktiviert.',
                field='product',
                code='free_mapping_pending',
            ),
            409,
        )
    try:
        _require_pro_access(request)
        task_id = str(body.get('task_id') or '').strip()
        if not task_id:
            raise PromptValidationError('task_id fehlt.', field='task_id', code='required')
        tier = str(body.get('microsoft_tier') or 'chatbasic').strip()
        payload = body.get('input') or {}
        if not isinstance(payload, dict):
            raise PromptValidationError('input muss ein Objekt sein.', field='input')
        result = compose_task(task_id=task_id, microsoft_tier=tier, payload=payload, product_code='PRO')
    except PromptValidationError as exc:
        status = 403 if exc.code in {'license_required', 'device_required', 'entitlement_required', 'tier_required'} else 400
        if exc.code == 'authentication_required':
            status = 401
        if exc.code == 'not_found':
            status = 404
        return _error(exc, status)

    response = JsonResponse(
        {
            'ok': True,
            'result': {
                'prompt': result.prompt,
                'ready': result.ready,
                'progress_percent': result.progress_percent,
                'task_id': result.task_id,
                'app_code': result.app_code,
                'policy_version': result.policy_version,
                'prompt_version': result.prompt_version,
                'persisted': False,
            },
        }
    )
    response['Cache-Control'] = 'no-store'
    return response


@require_POST
def rate(request, task_id):
    try:
        _require_pro_access(request)
    except PromptValidationError as exc:
        return _error(exc, 403 if exc.code != 'authentication_required' else 401)
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(PromptValidationError('Ungültiges JSON.', code='invalid_json'))
    try:
        version = published_version(task_id)
        stars = int(body.get('stars'))
        if stars < 1 or stars > 5:
            raise ValueError
    except PromptValidationError as exc:
        return _error(exc, 404 if exc.code == 'not_found' else 400)
    except (TypeError, ValueError):
        return _error(PromptValidationError('stars muss zwischen 1 und 5 liegen.', field='stars', code='choice'))
    feedback = str(body.get('feedback') or '').strip()
    try:
        rating, snapshot = save_rating(user=request.user, version=version, stars=stars, feedback=feedback)
    except ValueError as exc:
        return _error(PromptValidationError(str(exc), field='stars', code='choice'))
    response = JsonResponse({
        'ok': True,
        'rating': {
            'stars': rating.stars,
            'feedback_saved': bool(rating.feedback),
            'quality_status': snapshot.status,
            'recent_average': str(snapshot.recent_average) if snapshot.recent_average is not None else None,
            'rating_count': snapshot.rating_count,
        },
    })
    response['Cache-Control'] = 'no-store'
    return response
