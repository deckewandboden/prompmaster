#!/usr/bin/env python3
"""Offline contract checks for the GET-only production asset parity audit."""
from __future__ import annotations

import unittest
from pathlib import Path

from audit_public_asset_parity import (
    ASSET_BASENAME,
    ORIGIN,
    product_script_url,
    sha256,
)


class PublicAssetParityTests(unittest.TestCase):
    def test_exact_single_asset_and_query_parameter(self):
        html = (
            '<html><head><script src="/static/js/'
            + ASSET_BASENAME
            + '?v=release-123" defer></script></head></html>'
        )
        self.assertEqual(
            product_script_url(html),
            ORIGIN + "/static/js/" + ASSET_BASENAME + "?v=release-123",
        )

    def test_unrelated_scripts_do_not_count(self):
        html = (
            '<script src="/static/js/other.js"></script>'
            '<script src="/static/js/' + ASSET_BASENAME + '"></script>'
        )
        self.assertEqual(
            product_script_url(html),
            ORIGIN + "/static/js/" + ASSET_BASENAME,
        )

    def test_missing_script_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            product_script_url('<script src="/static/js/other.js"></script>')

    def test_duplicate_script_fails_closed(self):
        script = '<script src="/static/js/' + ASSET_BASENAME + '"></script>'
        with self.assertRaisesRegex(ValueError, "exactly one"):
            product_script_url(script * 2)

    def test_off_origin_script_fails_closed(self):
        html = '<script src="https://not-the-product.example/static/js/' + ASSET_BASENAME + '"></script>'
        with self.assertRaisesRegex(ValueError, "expected HTTPS origin"):
            product_script_url(html)

    def test_reference_sha256(self):
        self.assertEqual(
            sha256(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_checkout_asset_exists_and_is_not_empty(self):
        root = Path(__file__).resolve().parents[1]
        asset = root / "backend/static/js" / ASSET_BASENAME
        self.assertGreater(asset.stat().st_size, 100_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
