from __future__ import annotations

import json
import uuid

from django.core.exceptions import ValidationError
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.audit.services import audit
from apps.ops.auth import service_account
from apps.prompts.composer_core import PromptValidationError
from apps.prompts.lifecycle import clone_as_draft, run_version_tests
from apps.prompts.models import PromptDefinition, PromptVersion
from apps.prompts.services import build_spec, build_spec_for_version, compose_version

PROTOCOL_VERSION = '2025-03-26'
SERVER_INFO = {'name': 'netstyle-promptmaster-internal', 'version': '1.0.0'}
TOOLS = [
    {
        'name': 'prompt.read',
        'description': 'Liest eine veröffentlichte PromptDefinition/PromptVersion. Keine Änderung.',
        'inputSchema': {
            'type': 'object',
            'properties': {'task_id': {'type': 'string'}},
            'required': ['task_id'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'prompt.draft',
        'description': 'Erzeugt eine neue DRAFT-Version aus einer vorhandenen Version. Kein Publish.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'task_id': {'type': 'string'},
                'source_version': {'type': 'integer', 'minimum': 1},
            },
            'required': ['task_id'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'prompt.test',
        'description': 'Führt gespeicherte Tests aus oder komponiert eine nicht persistierte Preview. Kein Publish/Delete.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'version_id': {'type': 'string'},
                'microsoft_tier': {'type': 'string'},
                'payload': {'type': 'object'},
            },
            'required': ['version_id'],
            'additionalProperties': False,
        },
    },
]


def _json_rpc(result=None, *, request_id=None, error=None, status=200, request=None):
    body = {'jsonrpc': '2.0', 'id': request_id}
    if error is not None:
        body['error'] = error
    else:
        body['result'] = result
    accept = (request.headers.get('Accept', '') if request else '')
    if request and 'text/event-stream' in accept:
        encoded = json.dumps(body, ensure_ascii=False)
        response = StreamingHttpResponse(iter([f'event: message\ndata: {encoded}\n\n']), content_type='text/event-stream')
        response.status_code = status
    else:
        response = JsonResponse(body, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _find_account(request, scopes):
    for scope in scopes:
        account = service_account(request, scope)
        if account:
            return account, scope
    return None, None


def _error(code, message, data=None):
    payload = {'code': code, 'message': message}
    if data is not None:
        payload['data'] = data
    return payload


def _content(value):
    return [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False, indent=2, default=str)}]


@require_GET
def health(request):
    account, _ = _find_account(request, ['ops.read', 'prompt.read', 'prompt.draft', 'prompt.test'])
    if not account:
        return JsonResponse({'status': 'unauthorized'}, status=401)
    seeded = PromptDefinition.objects.filter(active=True).count()
    published = PromptVersion.objects.filter(lifecycle='PUBLISHED').count()
    status = 'ok' if seeded == 194 and published >= 194 else 'degraded'
    response = JsonResponse({
        'status': status,
        'service': 'promptmaster-mcp',
        'transport': 'streamable-http',
        'protocol_version': PROTOCOL_VERSION,
        'definitions': seeded,
        'published_versions': published,
        'tools': [tool['name'] for tool in TOOLS],
        'publish_tool': False,
        'delete_tool': False,
    }, status=200 if status == 'ok' else 503)
    response['Cache-Control'] = 'no-store'
    return response


@csrf_exempt
def endpoint(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'method_not_allowed'}, status=405)
    account, _ = _find_account(request, ['prompt.read', 'prompt.draft', 'prompt.test'])
    if not account:
        return _json_rpc(error=_error(-32001, 'Unauthorized'), request_id=None, status=401, request=request)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json_rpc(error=_error(-32700, 'Parse error'), request_id=None, status=400, request=request)

    if not isinstance(payload, dict):
        return _json_rpc(error=_error(-32600, 'Invalid Request'), status=400, request=request)
    request_id = payload.get('id')
    method = payload.get('method')
    params = payload.get('params') or {}
    if payload.get('jsonrpc') != '2.0' or not isinstance(method, str) or not isinstance(params, dict):
        return _json_rpc(error=_error(-32600, 'Invalid Request'), request_id=request_id, status=400, request=request)

    if method == 'initialize':
        return _json_rpc(
            {
                'protocolVersion': PROTOCOL_VERSION,
                'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': SERVER_INFO,
                'instructions': 'Interner PromptMaster-MCP. Erlaubt: read/draft/test. Kein publish/delete.',
            },
            request_id=request_id,
            request=request,
        )
    if method == 'notifications/initialized':
        return _json_rpc({}, request_id=request_id, request=request)
    if method == 'ping':
        return _json_rpc({}, request_id=request_id, request=request)
    if method == 'tools/list':
        allowed = set(account.scopes or [])
        tools = [tool for tool in TOOLS if tool['name'] in allowed]
        return _json_rpc({'tools': tools}, request_id=request_id, request=request)
    if method != 'tools/call':
        return _json_rpc(error=_error(-32601, 'Method not found'), request_id=request_id, status=404, request=request)

    name = str(params.get('name') or '')
    arguments = params.get('arguments') or {}
    if not isinstance(arguments, dict):
        return _json_rpc(error=_error(-32602, 'Invalid params'), request_id=request_id, status=400, request=request)
    if name not in {'prompt.read', 'prompt.draft', 'prompt.test'}:
        # Explicitly blocks publish/delete and every unapproved tool.
        return _json_rpc(error=_error(-32601, 'Tool not found'), request_id=request_id, status=404, request=request)
    if name not in (account.scopes or []):
        return _json_rpc(error=_error(-32003, 'Scope denied'), request_id=request_id, status=403, request=request)

    try:
        result = _call_tool(name, arguments, account, request)
    except (PromptValidationError, ValidationError, ValueError, TypeError) as exc:
        return _json_rpc(
            {'content': _content({'ok': False, 'error': str(exc)}), 'isError': True},
            request_id=request_id,
            request=request,
        )
    except (PromptDefinition.DoesNotExist, PromptVersion.DoesNotExist):
        return _json_rpc(
            {'content': _content({'ok': False, 'error': 'not_found'}), 'isError': True},
            request_id=request_id,
            request=request,
        )
    return _json_rpc({'content': _content(result), 'isError': False}, request_id=request_id, request=request)


def _call_tool(name, args, account, request):
    if name == 'prompt.read':
        task_id = str(args.get('task_id') or '').strip()
        if not task_id:
            raise ValueError('task_id fehlt')
        spec = build_spec(task_id)
        audit(None, 'mcp.prompt.read', account, {'task_id': task_id, 'service_account': str(account.id)}, request=request)
        return {'ok': True, 'prompt': spec}

    if name == 'prompt.draft':
        task_id = str(args.get('task_id') or '').strip()
        if not task_id:
            raise ValueError('task_id fehlt')
        definition = PromptDefinition.objects.get(task_id=task_id, active=True)
        source = None
        if args.get('source_version') is not None:
            source = PromptVersion.objects.get(definition=definition, version=int(args['source_version']))
        draft = clone_as_draft(definition, source=source)
        audit(
            None,
            'mcp.prompt.draft',
            account,
            {'task_id': task_id, 'draft_id': str(draft.id), 'draft_version': draft.version, 'service_account': str(account.id)},
            request=request,
        )
        return {
            'ok': True,
            'task_id': task_id,
            'version_id': str(draft.id),
            'version': draft.version,
            'lifecycle': draft.lifecycle,
            'human_review_required': True,
        }

    version_id = str(args.get('version_id') or '').strip()
    try:
        uuid.UUID(version_id)
    except ValueError as exc:
        raise ValueError('version_id muss eine UUID sein') from exc
    version = PromptVersion.objects.select_related('definition').get(pk=version_id)
    if isinstance(args.get('payload'), dict):
        result = compose_version(
            version=version,
            microsoft_tier=str(args.get('microsoft_tier') or 'premium'),
            payload=args['payload'],
        )
        payload = {
            'ok': True,
            'mode': 'preview',
            'task_id': version.definition.task_id,
            'version': version.version,
            'prompt': result.prompt,
            'progress_percent': result.progress_percent,
            'persisted': False,
        }
    else:
        summary = run_version_tests(version)
        payload = {
            'ok': summary.ok,
            'mode': 'testcases',
            'task_id': version.definition.task_id,
            'version': version.version,
            'total': summary.total,
            'passed': summary.passed,
            'failed': summary.failed,
            'errors': summary.errors,
        }
    audit(None, 'mcp.prompt.test', account, {
        key: payload[key] for key in ('ok', 'mode', 'task_id', 'version', 'total', 'passed', 'failed')
        if key in payload
    } | {'service_account': str(account.id)}, request=request)
    return payload
