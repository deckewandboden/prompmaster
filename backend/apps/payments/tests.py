from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from django.test import SimpleTestCase
from django.utils import timezone
from .services import calculate_refund
class RefundMathTests(SimpleTestCase):
    def test_full_remaining(self):
        now=timezone.now(); term=SimpleNamespace(paid_gross_amount=Decimal('35.88'),valid_from=now,valid_until=now+timedelta(days=365)); days,amount=calculate_refund(term,today=timezone.localdate(now));self.assertEqual(days,365);self.assertEqual(amount,Decimal('35.88'))
    def test_halfish_remaining_is_prorated(self):
        now=timezone.now(); term=SimpleNamespace(paid_gross_amount=Decimal('35.88'),valid_from=now-timedelta(days=265),valid_until=now+timedelta(days=100)); days,amount=calculate_refund(term,today=timezone.localdate(now));self.assertEqual(days,100);self.assertEqual(amount,Decimal('9.83'))
