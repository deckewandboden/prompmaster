
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
