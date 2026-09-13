from django.test import SimpleTestCase
from .totp import code,verify,new_secret
class TotpTests(SimpleTestCase):
    def test_totp_at_known_time(self):
        s=new_secret();t=1_000_000_000;c=code(s,at=t);self.assertEqual(len(c),6);self.assertTrue(verify(s,c,window=0,at=t));self.assertFalse(verify(s,'999999' if c!='999999' else '888888',window=0,at=t))
