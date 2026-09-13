from django.test import RequestFactory,SimpleTestCase
from .security import token_pair,token_hash
class SecurityTests(SimpleTestCase):
    def test_token_hash(self):
        raw,h=token_pair();self.assertEqual(token_hash(raw),h);self.assertNotEqual(raw,h)
