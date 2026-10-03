#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PREFIXES = ("archive/", ".github/workflows/")
SKIP_FILES = {
    "FILE_MANIFEST.tsv",
    "FILE_MANIFEST_AUDIT.tsv",
    "MANIFEST.json",
    "docs/COMPLETE_FILE_INVENTORY.md",
    "scripts/rebrand_promptfinisher.py",
    "scripts/validate_brand.py",
}
FORBIDDEN = ("PromptMaster", "PROMPTMASTER", "Promptmaster", "Prompt Master")


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [
        raw.decode("utf-8", errors="surrogateescape")
        for raw in result.stdout.split(b"\0")
        if raw
    ]


violations: list[str] = []
for rel in tracked_files():
    if rel in SKIP_FILES or any(rel.startswith(prefix) for prefix in SKIP_PREFIXES):
        continue
    path = ROOT / rel
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for token in FORBIDDEN:
        if token in text:
            lines = [
                str(index)
                for index, line in enumerate(text.splitlines(), start=1)
                if token in line
            ][:8]
            violations.append(f"{rel}: {token!r} in line(s) {', '.join(lines)}")

if violations:
    print("BRAND VALIDATION FAIL: obsolete product name remains in active repository files")
    for violation in violations:
        print(f" - {violation}")
    raise SystemExit(1)

print("BRAND VALIDATION OK: active product uses PROMPTFINISHER; historical archive/inventory paths excluded")
