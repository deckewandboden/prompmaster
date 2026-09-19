import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, HttpResponseNotFound
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.devices.services import register_device, validate_device_token
from .assets import GoldenMasterIntegrityError, read_verified_asset
from .forms import DeviceRegistrationForm
from .services import active_product_assignment, assignment_expiry_context, has_internal_staff_access, DEVICE_COOKIE, LEGACY_DEVICE_COOKIE

logger = logging.getLogger(__name__)


def _device_cookie(request):
    return request.COOKIES.get(DEVICE_COOKIE) or request.COOKIES.get(LEGACY_DEVICE_COOKIE, '')


def _set_device_cookie(response, raw):
    response.set_cookie(
        DEVICE_COOKIE, raw, max_age=400 * 24 * 60 * 60,
        secure=settings.SESSION_COOKIE_SECURE, httponly=True,
        samesite='Lax', path='/',
    )
    response.delete_cookie(LEGACY_DEVICE_COOKIE, path='/pro/', samesite='Lax')
    return response


def _user_agent_families(request):
    ua = request.META.get('HTTP_USER_AGENT', '')[:500].lower()
    if 'windows' in ua:
        os_family = 'Windows'
    elif 'android' in ua:
        os_family = 'Android'
    elif 'iphone' in ua or 'ipad' in ua:
        os_family = 'iOS/iPadOS'
    elif 'mac os' in ua or 'macintosh' in ua:
        os_family = 'macOS'
    elif 'linux' in ua:
        os_family = 'Linux'
    else:
        os_family = 'Unbekannt'

    if 'edg/' in ua:
        browser = 'Edge'
    elif 'firefox/' in ua:
        browser = 'Firefox'
    elif 'chrome/' in ua or 'crios/' in ua:
        browser = 'Chrome'
    elif 'safari/' in ua:
        browser = 'Safari'
    else:
        browser = 'Browser'
    return os_family, browser


def _access(request):
    assignment = active_product_assignment(request.user, 'PRO')
    if not assignment:
        return None, None
    token = _device_cookie(request)
    device = validate_device_token(request.user, token, product_code='PRO')
    if device and device.license_id != assignment.license_id:
        # License reassignment should already revoke the old credential. Treat
        # any remaining mismatch conservatively and require registration again.
        device = None
    return assignment, device


@login_required
def launch(request):
    if has_internal_staff_access(request.user):
        return redirect('proaccess:content')
    assignment, device = _access(request)
    if not assignment:
        messages.error(request, 'Für dieses Benutzerkonto ist keine aktive PromptMaster-Pro-Lizenz zugewiesen.')
        return redirect('portal:licenses')
    if not device:
        return redirect('proaccess:register_device')
    expiry = assignment_expiry_context(assignment)
    if expiry and expiry['level'] == 'critical':
        ack_key = f"{assignment.license_id}:{expiry['valid_until'].isoformat()}"
        if request.session.get('pro_critical_warning_ack') != ack_key:
            return redirect('proaccess:renewal_warning')
    return redirect('proaccess:content')


@login_required
def register_device_view(request):
    if has_internal_staff_access(request.user):
        return redirect('proaccess:content')
    assignment = active_product_assignment(request.user, 'PRO')
    if not assignment:
        raise PermissionDenied
    current = validate_device_token(request.user, _device_cookie(request), product_code='PRO')
    if current and current.license_id == assignment.license_id:
        return redirect('proaccess:content')

    os_family, browser_family = _user_agent_families(request)
    suggested = f'{os_family} · {browser_family}'
    form = DeviceRegistrationForm(request.POST or None, initial={'display_name': suggested})
    if request.method == 'POST' and form.is_valid():
        try:
            _device, raw = register_device(
                request.user,
                assignment.license,
                form.cleaned_data['display_name'],
                os_family=os_family,
                browser_family=browser_family,
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            response = redirect('proaccess:content')
            return _set_device_cookie(response, raw)
    return render(
        request,
        'proaccess/register_device.html',
        {'form': form, 'license': assignment.license, 'device_limit': assignment.license.product.default_device_limit},
    )


@login_required
def renewal_warning(request):
    if has_internal_staff_access(request.user):
        return redirect('proaccess:content')
    assignment, device = _access(request)
    if not assignment:
        return redirect('portal:licenses')
    if not device:
        return redirect('proaccess:register_device')
    expiry = assignment_expiry_context(assignment)
    if not expiry or expiry['level'] != 'critical':
        return redirect('proaccess:content')
    ack_key = f"{assignment.license_id}:{expiry['valid_until'].isoformat()}"
    if request.method == 'POST':
        request.session['pro_critical_warning_ack'] = ack_key
        return redirect('proaccess:content')
    return render(
        request,
        'proaccess/renewal_warning.html',
        {'assignment': assignment, 'expiry': expiry},
    )


@login_required
@xframe_options_sameorigin
def content(request):
    internal_staff = has_internal_staff_access(request.user)
    assignment, device = (None, None) if internal_staff else _access(request)
    if not internal_staff and not assignment:
        raise PermissionDenied
    if not internal_staff and not device:
        return redirect('proaccess:register_device')

    # Serve the deterministic runtime derivative. The exact Golden Master stays
    # immutable as the regression reference; the runtime bridge routes actual
    # composition/ratings to the versioned server domain.
    try:
        data = read_verified_asset(settings.PRO_RUNTIME_PATH, settings.PRO_RUNTIME_SHA256)
    except GoldenMasterIntegrityError:
        logger.exception('PromptMaster Pro runtime asset failed integrity validation')
        return render(request, 'proaccess/asset_missing.html', status=503)
    csrf_token = get_token(request)
    marker = b'__PM_CSRF_TOKEN__'
    if marker not in data:
        logger.error('PromptMaster Pro runtime asset is missing CSRF placeholder')
        return render(request, 'proaccess/asset_missing.html', status=503)
    data = data.replace(marker, csrf_token.encode('ascii'))

    # The verified runtime asset remains immutable on disk. Add only
    # session-navigation links to the delivered response so users who land
    # directly in Pro can return to their own security domain or sign out.
    utility_marker = b'<div class="utility"><div class="max">'
    if utility_marker not in data:
        logger.error('PromptMaster Pro runtime asset is missing utility navigation marker')
        return render(request, 'proaccess/asset_missing.html', status=503)
    workspace_url = (
        reverse('ns_admin:dashboard')
        if internal_staff
        else reverse('portal:dashboard')
    )
    workspace_label = 'netstyle Admin' if internal_staff else 'Kundenportal'
    session_links = (
        f'<a href="{workspace_url}">{workspace_label}</a>'
        f'<a href="{reverse("accounts:logout")}">Abmelden</a>'
    ).encode('utf-8')
    data = data.replace(utility_marker, utility_marker + session_links, 1)

    response = HttpResponse(data, content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'private, no-store'
    if not internal_staff and not request.COOKIES.get(DEVICE_COOKIE):
        _set_device_cookie(response, _device_cookie(request))
    return response


def free_content(request):
    """Serve FREE 1.2.4 with the additive 34-app visibility bridge.

    The reviewed Golden Master remains byte-verified and unchanged. The bridge
    only augments catalog visibility at runtime: the 16 reviewed Free task
    contracts keep their original local composition logic; all additional
    PromptDomain applications are visible but Pro-locked.
    """
    try:
        data = read_verified_asset(settings.FREE_GOLDEN_MASTER_PATH, settings.FREE_GOLDEN_MASTER_SHA256)
    except GoldenMasterIntegrityError:
        logger.exception('PromptMaster Free Golden Master failed integrity validation')
        return HttpResponse('PromptMaster Free ist vorübergehend nicht verfügbar.', status=503)

    marker = b'</body></html>'
    bridge = b'<script src="/static/js/free_catalog_bridge.20260918.js" defer></script>'
    if data.count(marker) != 1:
        logger.error('PromptMaster Free Golden Master has unexpected closing markup')
        return HttpResponse('PromptMaster Free ist vorübergehend nicht verfügbar.', status=503)
    data = data.replace(marker, bridge + marker)
    response = HttpResponse(data, content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=300'
    return response
