
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from .assets import GoldenMasterIntegrityError, read_verified_asset


class GoldenMasterAssetTests(SimpleTestCase):
    def test_verified_asset_accepts_exact_hash_and_rejects_drift(self):
        import hashlib

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'asset.html'
            path.write_bytes(b'<html>ok</html>')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(read_verified_asset(path, expected), b'<html>ok</html>')
            path.write_bytes(b'<html>changed</html>')
            with self.assertRaises(GoldenMasterIntegrityError):
                read_verified_asset(path, expected)


from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from .services import has_internal_staff_access


class InternalStaffProAccessTests(TestCase):
    def test_active_staff_has_internal_pro_access_without_customer_license(self):
        user = User.objects.create_user(
            'staff-pro@example.test',
            'Valid-Staff-Pro-Password-2026!',
            first_name='Netstyle',
            last_name='Staff',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='configured-for-test',
        )
        self.assertTrue(has_internal_staff_access(user))

        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

        response = self.client.get(reverse('proaccess:launch'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('proaccess:content'))

        response = self.client.get(reverse('proaccess:content'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/ns-admin/"')
        self.assertContains(response, 'href="/auth/logout/"')

    def test_customer_identity_does_not_receive_internal_access(self):
        user = User.objects.create_user(
            'customer-pro@example.test',
            'Valid-Customer-Pro-Password-2026!',
            first_name='Customer',
            last_name='User',
        )
        self.assertFalse(has_internal_staff_access(user))
