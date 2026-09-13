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

    def test_admin_can_open_faq_management(self):
        client = Client()
        client.force_login(self.admin)
        response = client.get('/ns-admin/content/faqs/')
        self.assertEqual(response.status_code, 200)
