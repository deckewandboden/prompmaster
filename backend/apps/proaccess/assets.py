from __future__ import annotations

import hashlib
from pathlib import Path


class GoldenMasterIntegrityError(RuntimeError):
    pass


def read_verified_asset(path_value, expected_sha256: str) -> bytes:
    """Read a product Golden Master only when its byte hash is exact.

    Product files are release-controlled assets. A missing or modified file must
    fail closed instead of serving an unreviewed Free/Pro implementation.
    """
    path = Path(path_value)
    if not path.is_file():
        raise GoldenMasterIntegrityError(f'Golden-Master-Datei fehlt: {path}')
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    expected = str(expected_sha256 or '').strip().lower()
    if not expected or actual != expected:
        raise GoldenMasterIntegrityError(
            f'Golden-Master-Hash stimmt nicht: {path.name} actual={actual} expected={expected or "<leer>"}'
        )
    return data
