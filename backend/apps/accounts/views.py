import secrets
from urllib.parse import quote, urlsplit

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.core.crypto import decrypt, encrypt
from apps.core.security import check_rate, client_ip, token_hash
from apps.notifications.services import queue_email
from apps.legal.models import LegalAcceptance, LegalDocument
from .forms import (
    AcceptInvitationForm,
    LoginForm,
    OtpForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    RecoveryCodesRegenerateForm,
    RegistrationForm,
)
from .models import RecoveryCode, User
from .security import bind_security_session, bump_security_version, consume_second_factor
from .totp import new_secret, matching_step
from apps.audit.services import audit

EMAIL_VERIFY_SALT = 'pm-email-verify'
PASSWORD_RESET_SALT = 'pm-password-reset'


def _safe_next(request, value=None):
    next_url = value if value is not None else (request.POST.get('next') or request.GET.get('next') or '')
    parts = urlsplit(next_url)
    if not parts.scheme and not parts.netloc and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return ''


@transaction.atomic
def _new_recovery_codes(user):
    type(user).objects.select_for_update().get(pk=user.pk)
    user.recovery_codes.all().delete()
    codes = [secrets.token_urlsafe(9) for _ in range(10)]
    RecoveryCode.objects.bulk_create(
        [RecoveryCode(user=user, code_hash=make_password(code)) for code in codes]
    )
    return codes


def login_view(request):
    limited = check_rate(request, 'login', 10, 300)
    if limited:
        return limited
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.user)
        request.session.cycle_key()
        bind_security_session(request, form.user, two_factor_ok=not form.user.two_factor_required)
        request.session['authenticated_at'] = timezone.now().timestamp()
        audit(form.user, 'auth.login', form.user, {'second_factor_pending': form.user.two_factor_required}, request=request)
        next_url = _safe_next(request)
        if form.user.two_factor_required:
            request.session['post_2fa_next'] = next_url or reverse('home')
            return redirect('accounts:two_factor')
        return redirect(next_url or 'home')
    return render(request, 'auth/login.html', {'form': form, 'next': _safe_next(request)})


@login_required
def logout_view(request):
    if request.method != 'POST':
        return render(request, 'auth/logout_confirm.html')
    logout(request)
    return redirect('accounts:login')


@transaction.atomic
def register(request):
    limited = check_rate(request, 'register', 5, 3600)
    if limited:
        return limited
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        now = timezone.now()
        legal_documents = {}
        for doc_type in ('terms', 'privacy'):
            document = (
                LegalDocument.objects.filter(doc_type=doc_type, active=True, valid_from__lte=now)
                .order_by('-valid_from')
                .first()
            )
            if not document:
                form.add_error(None, f'Registrierung ist vorübergehend nicht möglich: aktives Rechtsdokument fehlt ({doc_type}).')
                break
            legal_documents[doc_type] = document
        if form.errors:
            return render(request, 'auth/register.html', {'form': form})
        if User.objects.filter(email__iexact=data['email']).exists():
            form.add_error('email', 'E-Mail-Adresse bereits registriert.')
        else:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        email=data['email'],
                        password=data['password'],
                        first_name=data['first_name'].strip(),
                        last_name=data['last_name'].strip(),
                        two_factor_required=(data['customer_type'] == 'company'),
                    )
                    if data['customer_type'] == 'company':
                        company = Company.objects.create(
                            customer_number=f'C-{user.id.hex[:24].upper()}',
                            name=data['company_name'].strip(),
                            email=user.email,
                        )
                        Membership.objects.create(company=company, user=user, role='admin', active=True)
                    else:
                        PrivateCustomerProfile.objects.create(
                            user=user,
                            customer_number=f'P-{user.id.hex[:24].upper()}',
                        )
                    evidence = {
                        'ip': client_ip(request),
                        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:300],
                        'source': 'registration',
                    }
                    for document in legal_documents.values():
                        LegalAcceptance.objects.create(
                            user=user, document=document, order=None, evidence=evidence
                        )
            except IntegrityError:
                form.add_error('email', 'Konto konnte nicht angelegt werden. Bitte erneut versuchen.')
            else:
                token = signing.dumps({'uid': str(user.id), 'email': user.email}, salt=EMAIL_VERIFY_SALT)
                url = request.build_absolute_uri(reverse('accounts:verify_email', args=[token]))
                queue_email('verify_email', user.email, {'url': url}, scope_user=user)
                login(request, user)
                request.session.cycle_key()
                bind_security_session(request, user, two_factor_ok=not user.two_factor_required)
                messages.success(request, 'Konto angelegt. Bitte E-Mail-Adresse bestätigen.')
                return redirect('accounts:two_factor_setup' if user.two_factor_required else 'portal:dashboard')
    return render(request, 'auth/register.html', {'form': form})


def verify_email(request, token):
    try:
        data = signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=86400)
        user = User.objects.get(pk=data['uid'], email=data['email'])
    except (signing.BadSignature, signing.SignatureExpired, User.DoesNotExist, KeyError):
        return render(request, 'auth/verify_result.html', {'ok': False})
    if not user.email_verified_at:
        user.email_verified_at = timezone.now()
        user.save(update_fields=['email_verified_at', 'updated_at'])
    return render(request, 'auth/verify_result.html', {'ok': True})


@login_required
def two_factor(request):
    if not request.user.two_factor_required:
        request.session['two_factor_ok'] = True
        return redirect(_safe_next(request, request.session.pop('post_2fa_next', '')) or 'home')
    if request.session.get('two_factor_ok'):
        return redirect(_safe_next(request, request.session.pop('post_2fa_next', '')) or 'home')
    if not request.user.totp_secret_enc:
        return redirect('accounts:two_factor_setup')

    limited = check_rate(request, f'2fa:{request.user.pk}', 10, 300)
    if limited:
        return limited
    form = OtpForm(request.POST or None)
    error = ''
    if request.method == 'POST' and form.is_valid():
        value = form.cleaned_data['code'].strip()
        try:
            ok = consume_second_factor(request.user, value)
        except Exception:
            ok = False
        if ok:
            request.session.cycle_key()
            bind_security_session(request, request.user, two_factor_ok=True)
            audit(request.user, 'auth.second_factor', request.user, {}, request=request)
            next_url = _safe_next(request, request.session.pop('post_2fa_next', ''))
            return redirect(next_url or 'home')
        error = 'Code ungültig.'
    return render(request, 'auth/two_factor.html', {'form': form, 'error': error})


@login_required
@transaction.atomic
def two_factor_setup(request):
    request.user = User.objects.select_for_update().get(pk=request.user.pk)
    if request.user.totp_secret_enc:
        return redirect('portal:security')
    request.session.pop('pending_totp', None)
    pending = request.session.get('pending_totp_enc')
    secret = decrypt(pending) if pending else new_secret()
    request.session['pending_totp_enc'] = encrypt(secret)
    if request.method == 'POST':
        limited = check_rate(request, f'2fa-setup:{request.user.pk}', 10, 300)
        if limited:
            return limited
        value = request.POST.get('code', '')
        step = matching_step(secret, value)
        if step is not None:
            request.user.totp_secret_enc = encrypt(secret)
            request.user.two_factor_required = True
            request.user.last_totp_step = step
            request.user.save(update_fields=['totp_secret_enc', 'two_factor_required', 'last_totp_step', 'updated_at'])
            bump_security_version(request.user)
            codes = _new_recovery_codes(request.user)
            request.session.pop('pending_totp_enc', None)
            request.session.cycle_key()
            bind_security_session(request, request.user, two_factor_ok=True)
            audit(request.user, 'auth.second_factor_enabled', request.user, {}, request=request)
            return render(request, 'auth/recovery_codes.html', {'codes': codes})
        messages.error(request, 'Code ungültig.')
    label = quote(f'PromptMaster:{request.user.email}', safe='')
    uri = f'otpauth://totp/{label}?secret={secret}&issuer=PromptMaster'
    return render(request, 'auth/two_factor_setup.html', {'secret': secret, 'uri': uri})


@login_required
@transaction.atomic
def regenerate_recovery_codes(request):
    request.user = User.objects.select_for_update().get(pk=request.user.pk)
    if not request.user.totp_secret_enc or not request.session.get('two_factor_ok'):
        return redirect('accounts:two_factor')
    form = RecoveryCodesRegenerateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if not request.user.check_password(form.cleaned_data['password']):
            form.add_error('password', 'Passwort falsch.')
        else:
            codes = _new_recovery_codes(request.user)
            bump_security_version(request.user)
            bind_security_session(request, request.user, two_factor_ok=True)
            audit(request.user, 'auth.recovery_regenerated', request.user, {}, request=request)
            return render(request, 'auth/recovery_codes.html', {'codes': codes})
    return render(request, 'auth/password_confirm.html', {'form': form, 'title': 'Recovery-Codes neu erzeugen'})


def password_reset_request(request):
    limited = check_rate(request, 'password-reset', 5, 3600)
    if limited:
        return limited
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = User.objects.filter(email__iexact=form.cleaned_data['email'], is_active=True).first()
        if user:
            token = signing.dumps({'uid': str(user.id), 'email': user.email, 'sv': int(user.security_version)}, salt=PASSWORD_RESET_SALT)
            url = request.build_absolute_uri(reverse('accounts:password_reset_confirm', args=[token]))
            queue_email('password_reset', user.email, {'url': url}, scope_user=user)
        # Deliberately identical response for existing and unknown addresses.
        return render(request, 'auth/password_reset_sent.html')
    return render(request, 'auth/password_reset_request.html', {'form': form})


@transaction.atomic
def password_reset_confirm(request, token):
    try:
        data = signing.loads(token, salt=PASSWORD_RESET_SALT, max_age=3600)
        user = User.objects.select_for_update().get(pk=data['uid'], email=data['email'], is_active=True)
        if int(data['sv']) != int(user.security_version):
            raise KeyError('password reset token already used or invalidated')
    except (signing.BadSignature, signing.SignatureExpired, User.DoesNotExist, KeyError, ValueError, TypeError):
        return render(request, 'auth/password_reset_result.html', {'ok': False})

    form = PasswordResetConfirmForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user.set_password(form.cleaned_data['password'])
        update_fields = ['password', 'updated_at']
        if not user.email_verified_at:
            user.email_verified_at = timezone.now()
            update_fields.append('email_verified_at')
        user.save(update_fields=update_fields)
        bump_security_version(user)
        audit(user, 'auth.password_reset', user, {}, request=request)
        return render(request, 'auth/password_reset_result.html', {'ok': True})
    return render(request, 'auth/password_reset_confirm.html', {'form': form})


def accept_invitation(request, token):
    from apps.companies.models import Invitation

    try:
        invitation = Invitation.objects.select_related('company').get(token_hash=token_hash(token))
    except Invitation.DoesNotExist:
        return render(request, 'auth/invite_result.html', {'ok': False})
    if not invitation.is_valid():
        return render(request, 'auth/invite_result.html', {'ok': False})

    existing = User.objects.filter(email__iexact=invitation.email).first()
    if existing:
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        if request.user.id != existing.id:
            return render(request, 'auth/invite_result.html', {'ok': False})
        if hasattr(existing, 'private_customer'):
            return render(request, 'auth/invite_result.html', {'ok': False, 'reason': 'customer_type_conflict'})
        if existing.company_memberships.filter(active=True).exclude(company=invitation.company).exists():
            return render(request, 'auth/invite_result.html', {'ok': False})
        if request.method != 'POST':
            return render(request, 'auth/invite_confirm.html', {'invitation': invitation})
        with transaction.atomic():
            existing = User.objects.select_for_update().get(pk=existing.pk)
            invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
            if not invitation.is_valid() or not invitation.company.status == 'active' or existing.company_memberships.filter(active=True).exclude(company=invitation.company).exists():
                return render(request, 'auth/invite_result.html', {'ok': False})
            Membership.objects.update_or_create(
                company=invitation.company,
                user=existing,
                defaults={'active': True, 'role': 'member'},
            )
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=['accepted_at', 'updated_at'])
        return render(request, 'auth/invite_result.html', {'ok': True})

    now = timezone.now()
    legal_documents = {}
    for doc_type in ('terms', 'privacy'):
        document = (
            LegalDocument.objects.filter(doc_type=doc_type, active=True, valid_from__lte=now)
            .order_by('-valid_from')
            .first()
        )
        if document is None:
            return render(
                request,
                'auth/invite_result.html',
                {'ok': False, 'reason': 'legal_configuration'},
                status=503,
            )
        legal_documents[doc_type] = document

    form = AcceptInvitationForm(
        request.POST or None,
        initial={'first_name': invitation.first_name, 'last_name': invitation.last_name},
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
            if not invitation.is_valid():
                return render(request, 'auth/invite_result.html', {'ok': False})
            if User.objects.filter(email__iexact=invitation.email).exists():
                return render(request, 'auth/invite_result.html', {'ok': False})
            user = User.objects.create_user(
                email=invitation.email,
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'].strip(),
                last_name=form.cleaned_data['last_name'].strip(),
                email_verified_at=timezone.now(),
            )
            Membership.objects.create(company=invitation.company, user=user, role='member', active=True)
            evidence = {
                'source': 'invitation',
                'ip': client_ip(request),
                'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:500],
            }
            for document in legal_documents.values():
                LegalAcceptance.objects.create(user=user, document=document, evidence=evidence)
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=['accepted_at', 'updated_at'])
            login(request, user)
            request.session.cycle_key()
            bind_security_session(request, user, two_factor_ok=True)
        return redirect('portal:dashboard')
    return render(
        request,
        'auth/accept_invitation.html',
        {'form': form, 'invitation': invitation, 'legal_documents': legal_documents},
    )
