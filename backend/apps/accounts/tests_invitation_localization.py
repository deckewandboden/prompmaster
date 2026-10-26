"""Rendered invitation-acceptance language contract for all ten UI locales.

Only the UI and existing links are localized. Unreviewed legal document
bodies are never treated as translated by these assertions.
"""
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.forms import AcceptInvitationForm


class InvitationAcceptanceLanguageTests(SimpleTestCase):
    HEADINGS = {
        'de': 'Einladung annehmen',
        'en': 'Accept invitation',
        'es': 'Aceptar invitación',
        'pt': 'Aceitar convite',
        'tr': 'Daveti kabul et',
        'ru': 'Принять приглашение',
        'pl': 'Przyjmij zaproszenie',
        'fr': 'Accepter l’invitation',
        'it': 'Accetta l’invito',
        'nl': 'Uitnodiging accepteren',
    }

    BUTTONS = {
        'de': 'Konto anlegen und Einladung annehmen',
        'en': 'Create account and accept invitation',
        'es': 'Crear cuenta y aceptar la invitación',
        'pt': 'Criar conta e aceitar convite',
        'tr': 'Hesap oluştur ve daveti kabul et',
        'ru': 'Создать учётную запись и принять приглашение',
        'pl': 'Utwórz konto i przyjmij zaproszenie',
        'fr': 'Créer un compte et accepter l’invitation',
        'it': 'Crea un account e accetta l’invito',
        'nl': 'Account aanmaken en uitnodiging accepteren',
    }

    def test_real_invitation_template_is_localized_and_legal_links_persist(self):
        request = RequestFactory().get('/auth/invitation/test/')
        request.user = AnonymousUser()
        invitation = SimpleNamespace(
            company=SimpleNamespace(name='Example GmbH'),
        )
        for language in self.HEADINGS:
            with self.subTest(language=language), override(language):
                html = render_to_string(
                    'auth/accept_invitation.html',
                    {'form': AcceptInvitationForm(), 'invitation': invitation},
                    request=request,
                )
                self.assertIn('lang="' + language + '"', html)
                self.assertIn(self.HEADINGS[language], html)
                self.assertIn(self.BUTTONS[language], html)
                self.assertIn('Example GmbH', html)
                self.assertIn('href="/legal/terms/"', html)
                self.assertIn('href="/legal/privacy/"', html)
                for field in ('first_name', 'last_name', 'password',
                              'accept_terms', 'accept_privacy'):
                    self.assertIn('name="' + field + '"', html)
                self.assertIn('type="submit"', html)
                if language != 'de':
                    self.assertNotIn('Einladung annehmen</h1>', html)
                    self.assertNotIn('>Konto anlegen und Einladung annehmen</button>', html)

    def test_existing_user_invitation_confirmation_in_all_languages(self):
        request = RequestFactory().get('/auth/invitation/confirm/')
        request.user = AnonymousUser()
        invitation = SimpleNamespace(
            company=SimpleNamespace(name='Example GmbH'),
        )
        for language in self.HEADINGS:
            with self.subTest(language=language), override(language):
                html = render_to_string(
                    'auth/invite_confirm.html',
                    {'invitation': invitation},
                    request=request,
                )
                self.assertIn('lang="' + language + '"', html)
                self.assertIn(self.HEADINGS[language], html)
                self.assertIn('Example GmbH', html)
                self.assertIn('type="submit"', html)
                if language != 'de':
                    self.assertNotIn('>Firma beitreten</button>', html)
                    self.assertNotIn(
                        'Der Beitritt erfolgt erst nach Ihrer ausdrücklichen Bestätigung.',
                        html,
                    )

    def test_invitation_outcome_pages_in_all_languages(self):
        request = RequestFactory().get('/auth/invitation/result/')
        request.user = AnonymousUser()
        for language in self.HEADINGS:
            for ok in (True, False):
                with self.subTest(language=language, ok=ok), override(language):
                    html = render_to_string(
                        'auth/invite_result.html', {'ok': ok}, request=request,
                    )
                    self.assertIn('lang="' + language + '"', html)
                    if ok:
                        self.assertIn('href="' + reverse('portal:dashboard') + '"', html)
                    else:
                        self.assertIn('href="' + reverse('home') + '"', html)
                    if language != 'de':
                        self.assertNotIn('>Einladung angenommen</h1>', html)
                        self.assertNotIn(
                            '>Einladung ungültig oder abgelaufen</h1>',
                            html,
                        )

    def test_email_verification_outcome_pages_in_all_languages(self):
        request = RequestFactory().get('/auth/verify/result/')
        request.user = AnonymousUser()
        for language in self.HEADINGS:
            for ok in (True, False):
                with self.subTest(language=language, ok=ok), override(language):
                    html = render_to_string(
                        'auth/verify_result.html',
                        {'ok': ok, 'continue_url': '/free/' if ok else None},
                        request=request,
                    )
                    self.assertIn('lang="' + language + '"', html)
                    if ok:
                        self.assertIn('href="/free/"', html)
                    else:
                        self.assertIn('href="' + reverse('accounts:login') + '"', html)
                    if language != 'de':
                        self.assertNotIn('>E-Mail bestätigt</h1>', html)
                        self.assertNotIn('>Link ungültig oder abgelaufen</h1>', html)
