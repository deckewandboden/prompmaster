from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase

from .models import FAQEntry


class FaqTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_faqs', verbosity=0)
        cls.admin = get_user_model().objects.create_superuser(
            email='faq-admin@example.invalid', password='TestPassword-12345!', first_name='FAQ', last_name='Admin'
        )

    def test_seed_and_public_api(self):
        self.assertEqual(FAQEntry.objects.filter(audience='public', active=True).count(), 6)
        response = Client().get('/api/v1/content/faqs/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 6)

    def _admin_client(self):
        client = Client()
        self.admin.two_factor_required = False
        self.admin.save(update_fields=["two_factor_required"])
        client.force_login(self.admin)
        session = client.session
        session["security_version"] = self.admin.security_version
        session["two_factor_ok"] = True
        session.save()
        return client

    def test_admin_can_open_faq_management(self):
        response = self._admin_client().get('/ns-admin/content/faqs/')
        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_edit_and_toggle_faq(self):
        client = self._admin_client()
        create = client.post(
            '/ns-admin/content/faqs/new/',
            {
                'key': 'pre-mollie-acceptance',
                'question': 'Funktioniert die FAQ-Verwaltung?',
                'answer': 'Ja, inklusive Erstellen, Bearbeiten und Statuswechsel.',
                'audience': 'customer',
                'sort_order': '77',
                'active': 'on',
            },
        )
        self.assertEqual(create.status_code, 302)
        faq = FAQEntry.objects.get(key='pre-mollie-acceptance')
        self.assertTrue(faq.active)

        edit = client.post(
            f'/ns-admin/content/faqs/{faq.pk}/',
            {
                'key': faq.key,
                'question': 'Funktioniert die FAQ-Verwaltung vollständig?',
                'answer': 'Mutation erfolgreich geprüft.',
                'audience': 'pro',
                'sort_order': '78',
                'active': 'on',
            },
        )
        self.assertEqual(edit.status_code, 302)
        faq.refresh_from_db()
        self.assertEqual(faq.question, 'Funktioniert die FAQ-Verwaltung vollständig?')
        self.assertEqual(faq.audience, 'pro')
        self.assertEqual(faq.sort_order, 78)

        toggle = client.post(f'/ns-admin/content/faqs/{faq.pk}/toggle/')
        self.assertEqual(toggle.status_code, 302)
        faq.refresh_from_db()
        self.assertFalse(faq.active)

    def test_faq_toggle_is_not_executable_by_get(self):
        client = self._admin_client()
        faq = FAQEntry.objects.filter(active=True).first()
        response = client.get(f'/ns-admin/content/faqs/{faq.pk}/toggle/')
        self.assertEqual(response.status_code, 403)
        faq.refresh_from_db()
        self.assertTrue(faq.active)
