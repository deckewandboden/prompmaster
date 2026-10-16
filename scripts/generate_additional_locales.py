"""Create reviewed-input, machine-translated gettext draft catalogs.

Only repository-local public UI strings are translated. The Argos models run
on the GitHub runner; no customer requests, customer data or secrets are sent
to a translation service. Translation quality still needs native QA.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import argostranslate.package
import argostranslate.translate
import polib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/locale/en/LC_MESSAGES/django.po"
TARGETS = {
    "pl": "nplurals=3; plural=(n==1 ? 0 : (n%10>=2 && n%10<=4 && (n%100<12 || n%100>14)) ? 1 : 2);",
    "fr": "nplurals=2; plural=(n>1);",
    "it": "nplurals=2; plural=(n!=1);",
    "nl": "nplurals=2; plural=(n!=1);",
}
# Keep machine translators from altering format placeholders and product names.
PROTECTED = re.compile(
    r"%[(][A-Za-z_][A-Za-z0-9_]*[)][a-zA-Z]"
    r"|[{][A-Za-z_][A-Za-z0-9_]*[}]"
    r"|PROMPTFINISHER|Microsoft 365 Copilot|Microsoft Copilot"
    r"|Mollie|netstyle",
    re.IGNORECASE,
)


def protect(value: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def replace(match: re.Match[str]) -> str:
        tokens.append(match.group())
        return f"ZZPFKEEP{len(tokens):04d}ZZ"

    return PROTECTED.sub(replace, value), tokens


def translate_preserving(value: str, translator) -> tuple[str, bool]:
    if not value or not any(c.isalpha() for c in value):
        return value, True
    safe, tokens = protect(value)
    translated = translator.translate(safe)
    for i, original in enumerate(tokens, start=1):
        marker = f"ZZPFKEEP{i:04d}ZZ"
        # The placeholder must be byte-identical; otherwise use the approved
        # English wording rather than shipping broken interpolation syntax.
        if translated.count(marker) != 1:
            return value, False
        translated = translated.replace(marker, original)
    if sorted(PROTECTED.findall(translated)) != sorted(PROTECTED.findall(value)):
        return value, False
    named = re.compile(r"%[(][A-Za-z_][A-Za-z0-9_]*[)][a-zA-Z]")
    if sorted(named.findall(translated)) != sorted(named.findall(value)):
        return value, False
    if not translated.strip() or len(translated) > max(4500, 4 * len(value)):
        return value, False
    return translated.strip(), True


def main(codes: list[str]) -> None:
    catalog = polib.pofile(str(SOURCE), check_for_duplicates=True)
    argostranslate.package.update_package_index()
    packages = argostranslate.package.get_available_packages()
    for code in codes:
        if code not in TARGETS:
            raise SystemExit(f"Unsupported language: {code}")
        candidates = [
            package for package in packages
            if package.from_code == "en" and package.to_code == code
        ]
        if not candidates:
            raise SystemExit(f"No verified English -> {code} Argos model in the index")
        model = candidates[0]
        print(f"Installing offline Argos en->{code} model", flush=True)
        argostranslate.package.install_from_path(model.download())
        translator = argostranslate.translate.get_translation_from_codes("en", code)
        existing_path = ROOT / "backend/locale" / code / "LC_MESSAGES/django.po"
        existing = (
            {item.msgid: item.msgstr for item in polib.pofile(str(existing_path))}
            if existing_path.is_file() else {}
        )
        out = polib.POFile()
        out.metadata = dict(catalog.metadata)
        out.metadata.update({
            "Language": code,
            "Project-Id-Version": "PROMPTFINISHER",
            "Content-Type": "text/plain; charset=UTF-8",
            "Plural-Forms": TARGETS[code],
            "X-Translation-Method": "Argos offline machine translation - editorial QA pending",
        })
        fallbacks = 0
        changed = 0
        for entry in catalog:
            src = entry.msgstr or entry.msgid
            if not src:
                continue
            previous = existing.get(entry.msgid, '')
            expected = sorted(re.findall(r"%[(][A-Za-z_][A-Za-z0-9_]*[)][a-zA-Z]", entry.msgid))
            actual = sorted(re.findall(r"%[(][A-Za-z_][A-Za-z0-9_]*[)][a-zA-Z]", previous))
            if previous and expected == actual:
                translated, valid = previous, True  # protect editorial corrections
            else:
                translated, valid = translate_preserving(src, translator)
            if not valid:
                fallbacks += 1
            elif translated != src:
                changed += 1
            out.append(polib.POEntry(
                msgid=entry.msgid,
                msgstr=translated,
                occurrences=entry.occurrences,
                comment=entry.comment,
                tcomment=entry.tcomment,
                flags=sorted(set(
                    [flag for flag in entry.flags if flag != "fuzzy"] +
                    (["python-format"] if re.search(
                        r"%[(][A-Za-z_][A-Za-z0-9_]*[)][a-zA-Z]", entry.msgid
                    ) else [])
                )),
            ))
        target = ROOT / "backend/locale" / code / "LC_MESSAGES/django.po"
        target.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(target))
        checked = polib.pofile(str(target), check_for_duplicates=True)
        assert len(checked) == len(catalog), (code, len(checked), len(catalog))
        assert all(item.msgstr for item in checked)
        print(
            f"LANGUAGE={code} ENTRIES={len(checked)} CHANGED={changed} "
            f"FALLBACK_ENGLISH={fallbacks} QUALITY=REVIEW_REQUIRED",
            flush=True,
        )
        if fallbacks > 15:
            raise SystemExit(f"Too many unsafe placeholder translations in {code}: {fallbacks}")


if __name__ == "__main__":
    codes = sys.argv[1:] or list(TARGETS)
    main(codes)
