#!/usr/bin/env python3
"""Check exact Marketing and Backend early-performance consent versions.

Run against the full repository checkout. The Django runtime image does not
contain marketing/src, so this belongs in the source-guard CI stage rather
than Django's containerized test suite.
"""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = ("de", "en", "es", "pt", "tr", "ru", "pl", "fr", "it", "nl")
CLAUSE_ID = "early-performance-services-2026-v1"


def backend_clauses() -> dict[str, str]:
    path = ROOT / "backend/apps/legal/checkout_clause.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    version = None
    clauses = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "CLAUSE_ID" in targets:
            version = ast.literal_eval(node.value)
        if "EARLY_PERFORMANCE_STATEMENTS" in targets:
            clauses = ast.literal_eval(node.value)
    if version != CLAUSE_ID or not isinstance(clauses, dict):
        raise AssertionError("Early-performance clause version or mapping missing")
    return clauses


class EarlyPerformanceCopySyncTests(unittest.TestCase):
    def test_marketing_matches_all_backend_clauses_character_for_character(self):
        clauses = backend_clauses()
        self.assertEqual(set(clauses), set(SUPPORTED))
        self.assertTrue(all(isinstance(value, str) and value.strip() for value in clauses.values()))

        marketing_dir = ROOT / "marketing/src"
        translations = (marketing_dir / "locale.js").read_text(encoding="utf-8")
        literal_key = json.dumps(clauses["de"], ensure_ascii=False) + ":"
        self.assertEqual(
            translations.count(literal_key), 1,
            "Marketing source must declare the exact German checkbox text once",
        )
        index = translations.index(literal_key) + len(literal_key)
        localized, _end = json.JSONDecoder().raw_decode(translations[index:])
        self.assertEqual(
            localized,
            {key: clauses[key] for key in SUPPORTED if key != "de"},
        )
        content = (marketing_dir / "content.js").read_text(encoding="utf-8")
        self.assertIn(clauses["de"], content)
        self.assertIn('data-legal-early-performance-text', content)
        frontend = (marketing_dir / "main.js").read_text(encoding="utf-8")
        self.assertIn('snapshot.earlyPerformance.text', frontend)
        self.assertIn('statement.textContent=snapshot.earlyPerformance.text', frontend)


if __name__ == "__main__":
    unittest.main(verbosity=2)
