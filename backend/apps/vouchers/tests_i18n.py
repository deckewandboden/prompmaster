"""Ten-language voucher translation coverage and runtime gettext acceptance."""
from __future__ import annotations

import json
import re
from ast import literal_eval
from pathlib import Path

from django.test import SimpleTestCase
from django.utils.translation import gettext, override

from .models import Voucher, VoucherRedemption


ROOT = Path(__file__).resolve().parent
LANGUAGES = ("en", "es", "pt", "tr", "ru", "pl", "fr", "it", "nl")
PLACEHOLDER = re.compile(r"%\(([a-z_]+)\)s")


def read_entries(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = {}
    current = None
    for line in lines:
        if line.startswith("msgid ") and line != 'msgid ""':
            current = literal_eval(line[6:])
        elif line.startswith("msgstr ") and current is not None:
            if current in entries:
                raise AssertionError("Duplicate gettext key: " + current)
            entries[current] = literal_eval(line[7:])
            current = None
    return entries


class VoucherInternationalizationTests(SimpleTestCase):
    def test_all_canonical_strings_have_real_translations_in_nine_languages(self):
        rows = json.loads((ROOT / "translation_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 134)
        self.assertEqual(len({row["de"] for row in rows}), len(rows))
        for lang in LANGUAGES:
            path = ROOT / "locale" / lang / "LC_MESSAGES" / "django.po"
            contents = read_entries(path)
            self.assertEqual(set(contents), {row["de"] for row in rows}, lang)
            for row in rows:
                with self.subTest(lang=lang, key=row["de"]):
                    self.assertEqual(contents[row["de"]], row[lang])
                    self.assertTrue(row[lang].strip())
                    self.assertNotEqual(row[lang], row["de"])
                    self.assertEqual(
                        sorted(PLACEHOLDER.findall(row["de"])),
                        sorted(PLACEHOLDER.findall(contents[row["de"]])),
                    )

    def test_source_and_template_catalogs_never_regress(self):
        """All user-facing voucher strings stay translated in every locale."""
        source_paths = (
            ROOT / "forms.py", ROOT / "views.py", ROOT / "models.py",
            ROOT / "services.py",
            ROOT.parent.parent / "templates/ns_admin/vouchers.html",
            ROOT.parent.parent / "templates/ns_admin/voucher_form.html",
            ROOT.parent.parent / "templates/ns_admin/voucher_issued.html",
            ROOT.parent.parent / "templates/ns_admin/voucher_detail.html",
            ROOT.parent.parent / "templates/portal/vouchers.html",
        )
        strings = set()
        for path in source_paths:
            self.assertTrue(path.is_file(), str(path))
            content = path.read_text(encoding="utf-8")
            strings.update(re.findall(r"\{%\s*translate\s+[\"'](.+?)[\"']\s*%\}", content))
            strings.update(re.findall(r"_\(\s*[\"'](.+?)[\"']\s*\)", content))
        self.assertGreaterEqual(len(strings), 145)
        canonical_rows = json.loads((ROOT / "translation_catalog.json").read_text(encoding="utf-8"))
        canonical = {row["de"]: row for row in canonical_rows}
        for lang in LANGUAGES:
            global_entries = read_entries(
                ROOT.parent.parent / "locale" / lang / "LC_MESSAGES/django.po"
            )
            for string in strings:
                with self.subTest(lang=lang, key=string):
                    self.assertTrue(global_entries.get(string))
                    if string in canonical:
                        self.assertEqual(global_entries[string], canonical[string][lang])
                    # General UI terms such as "Status" legitimately have
                    # identical spelling in more than one language.

    def test_gettext_runtime_loads_each_app_level_locale(self):
        rows = json.loads((ROOT / "translation_catalog.json").read_text(encoding="utf-8"))
        sample = next(row for row in rows if row["de"] == "Gutscheine & Aktionen")
        for language in LANGUAGES:
            with override(language):
                self.assertEqual(gettext(sample["de"]), sample[language], language)

    def test_model_status_and_kind_choices_are_localized(self):
        rows = json.loads((ROOT / "translation_catalog.json").read_text(encoding="utf-8"))
        labels = {row["de"]: row for row in rows}
        for lang in LANGUAGES:
            with override(lang):
                self.assertEqual(str(dict(Voucher.KIND)["trial"]), labels["Kostenlose Pro-Laufzeit"][lang])
                self.assertEqual(
                    str(dict(VoucherRedemption.STATUS)["redeemed"]),
                    labels["Eingelöst"][lang],
                )
