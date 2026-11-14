"""Hermetic, no-network checks for the strict live public-route auditor."""
import unittest

from audit_public_routes_readonly import (
    BASE, PUBLIC_HTML, PROTECTED_REDIRECT, SENSITIVE_DENIED,
    first_party_https,
)


class PublicAuditSafetyTests(unittest.TestCase):
    def test_origin_rejects_non_https_and_off_site(self):
        self.assertTrue(first_party_https(BASE + "/free/"))
        self.assertFalse(first_party_https("http://promptmaster.decke-wand-boden.de/free/"))
        self.assertFalse(first_party_https("https://promptmaster.decke-wand-boden.de.evil.test/"))
        self.assertFalse(first_party_https("https://example.org/"))
        self.assertFalse(first_party_https("https://user:pass@promptmaster.decke-wand-boden.de/"))

    def test_each_route_has_single_expectation(self):
        groups = [set(PUBLIC_HTML), set(PROTECTED_REDIRECT), set(SENSITIVE_DENIED)]
        self.assertTrue(all(groups))
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                self.assertFalse(groups[a] & groups[b])
        self.assertGreaterEqual(len(set.union(*groups)), 25)


if __name__ == "__main__":
    unittest.main()
