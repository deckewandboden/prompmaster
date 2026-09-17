from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import Permission, Role


class RbacSeedContractTests(TestCase):
    def setUp(self):
        call_command('seed_defaults', verbosity=0)

    def permission_codes(self, role_code):
        return set(
            Role.objects.get(code=role_code)
            .permissions.values_list('code', flat=True)
        )

    def test_support_role_has_business_support_rights_without_privileged_secrets_or_roles(self):
        actual = self.permission_codes('support')
        required = {
            'customers.read', 'customers.write',
            'licenses.read', 'licenses.write',
            'devices.write', 'orders.read', 'payments.read',
            'support.read', 'support.write', 'audit.read',
        }
        forbidden = {
            'api.read', 'api.write', 'settings.read', 'settings.write',
            'roles.read', 'roles.write', 'payments.refund', 'ops.read',
        }
        self.assertTrue(required.issubset(actual))
        self.assertTrue(actual.isdisjoint(forbidden))

    def test_operations_role_has_ops_and_integration_read_without_business_mutation_rights(self):
        actual = self.permission_codes('ops')
        required = {'ops.read', 'api.read', 'audit.read'}
        forbidden = {
            'products.write', 'products.read', 'payments.refund',
            'payments.read', 'settings.write', 'roles.write',
            'customers.write', 'licenses.write', 'email.write',
        }
        self.assertTrue(required.issubset(actual))
        self.assertTrue(actual.isdisjoint(forbidden))

    def test_superadmin_role_contains_every_seeded_permission(self):
        all_permissions = set(Permission.objects.values_list('code', flat=True))
        self.assertEqual(self.permission_codes('superadmin'), all_permissions)

    def test_custom_roles_can_be_added_without_code_changes(self):
        read_only, _ = Role.objects.get_or_create(code='read_only', defaults={'name': 'Read Only'})
        permission = Permission.objects.get(code='customers.read')
        read_only.permissions.add(permission)
        self.assertTrue(read_only.permissions.filter(code='customers.read').exists())
