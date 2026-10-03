#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVES = {
    "backend/private_assets/promptmaster_free_reference.html": "backend/private_assets/promptfinisher_free_reference.html",
    "backend/private_assets/promptmaster_pro.html": "backend/private_assets/promptfinisher_pro.html",
    "backend/private_assets/promptmaster_pro_runtime.html": "backend/private_assets/promptfinisher_pro_runtime.html",
    "backend/static/brand/promptmaster-logo-clean.svg": "backend/static/brand/promptfinisher-logo-clean.svg",
    "backend/static/brand/promptmaster-logo-hq.png": "backend/static/brand/promptfinisher-logo-hq.png",
    "backend/static/brand/promptmaster-logo-reference.png": "backend/static/brand/promptfinisher-logo-reference.png",
    "backend/static/css/promptmaster_v2.20260922.css": "backend/static/css/promptfinisher_v2.20260922.css",
    "backend/static/js/promptmaster_brand_hq.20260925.js": "backend/static/js/promptfinisher_brand_hq.20260925.js",
    "backend/static/js/promptmaster_ui_v2.20260922.js": "backend/static/js/promptfinisher_ui_v2.20260922.js",
    "marketing/public/brand/promptmaster-logo-clean.svg": "marketing/public/brand/promptfinisher-logo-clean.svg",
    "marketing/public/brand/promptmaster-logo-hq.png": "marketing/public/brand/promptfinisher-logo-hq.png",
    "product/golden_masters/promptmaster_free.html": "product/golden_masters/promptfinisher_free.html",
    "product/golden_masters/promptmaster_pro.html": "product/golden_masters/promptfinisher_pro.html",
}
SKIP_PREFIXES = ("archive/", ".github/workflows/")
SELF = "scripts/rebrand_promptfinisher_assets.py"

for old, new in MOVES.items():
    old_path = ROOT / old
    new_path = ROOT / new
    if old_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", old, new], cwd=ROOT, check=True)
    elif not new_path.exists():
        raise SystemExit(f"Missing source and target: {old} -> {new}")

tracked = subprocess.run(
    ["git", "ls-files", "-z"],
    cwd=ROOT,
    check=True,
    stdout=subprocess.PIPE,
).stdout.split(b"\0")

replacements = []
for old, new in MOVES.items():
    replacements.append((old, new))
    replacements.append((Path(old).name, Path(new).name))

changed = 0
for raw in tracked:
    if not raw:
        continue
    rel = raw.decode("utf-8", errors="surrogateescape")
    if rel == SELF or any(rel.startswith(prefix) for prefix in SKIP_PREFIXES):
        continue
    path = ROOT / rel
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    updated = text
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        changed += 1

print(f"ASSET REBRAND OK: {len(MOVES)} paths moved; {changed} reference file(s) updated")
