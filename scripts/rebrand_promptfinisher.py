#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PREFIXES = ("archive/",)
SKIP_FILES = {
    "FILE_MANIFEST.tsv",
    "FILE_MANIFEST_AUDIT.tsv",
    "MANIFEST.json",
    "docs/COMPLETE_FILE_INVENTORY.md",
    "scripts/rebrand_promptfinisher.py",
    "scripts/validate_brand.py",
}
REPLACEMENTS = (
    ("Prompt Master", "PROMPTFINISHER"),
    ("PromptMaster", "PROMPTFINISHER"),
    ("PROMPTMASTER", "PROMPTFINISHER"),
    ("Promptmaster", "PROMPTFINISHER"),
)
HASH_TARGETS = (
    "backend/private_assets/promptmaster_free_reference.html",
    "backend/private_assets/promptmaster_pro.html",
    "backend/private_assets/promptmaster_pro_runtime.html",
    "product/golden_masters/promptmaster_free.html",
    "product/golden_masters/promptmaster_pro.html",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def active_text_files() -> list[Path]:
    files = []
    for rel in tracked_files():
        if rel in SKIP_FILES or any(rel.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(path)
    return files


def replace_everywhere(files: list[Path], replacements: tuple[tuple[str, str], ...]) -> tuple[int, int]:
    changed_files = 0
    replacements_done = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in replacements:
            count = updated.count(old)
            if count:
                replacements_done += count
                updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed_files += 1
    return changed_files, replacements_done


old_hashes = {
    rel: sha256(ROOT / rel)
    for rel in HASH_TARGETS
    if (ROOT / rel).is_file()
}
files = active_text_files()
changed, replaced = replace_everywhere(files, REPLACEMENTS)

# Newly changed branding lines must satisfy git diff --check. Some historical
# Markdown sources used two trailing spaces for a hard line break; once the
# line is changed by the rename, remove only that trailing whitespace.
whitespace_changed = 0
for path in files:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    updated_lines = []
    touched = False
    for line in lines:
        ending = "\n" if line.endswith("\n") else ""
        body = line[:-1] if ending else line
        if "PROMPTFINISHER" in body:
            clean = body.rstrip(" \t")
            if clean != body:
                touched = True
            body = clean
        updated_lines.append(body + ending)
    if touched:
        path.write_text("".join(updated_lines), encoding="utf-8")
        whitespace_changed += 1

new_hashes = {
    rel: sha256(ROOT / rel)
    for rel in HASH_TARGETS
    if (ROOT / rel).is_file()
}
hash_replacements = tuple(
    (old_hashes[rel], new_hashes[rel])
    for rel in HASH_TARGETS
    if rel in old_hashes
    and old_hashes[rel] != new_hashes[rel]
)
hash_changed, hash_replaced = replace_everywhere(files, hash_replacements)

manifest_json = ROOT / "MANIFEST.json"
if manifest_json.is_file():
    data = json.loads(manifest_json.read_text(encoding="utf-8"))
    data["project"] = "PROMPTFINISHER Commercial RC14 Full Repository"
    manifest_json.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

inventory = ROOT / "docs" / "COMPLETE_FILE_INVENTORY.md"
if inventory.is_file():
    text = inventory.read_text(encoding="utf-8")
    first, sep, rest = text.partition("\n")
    for old, new in REPLACEMENTS:
        first = first.replace(old, new)
    inventory.write_text(first + sep + rest, encoding="utf-8")

print(
    "REBRAND OK: "
    f"{changed} content file(s), {replaced} product-name replacement(s), "
    f"{whitespace_changed} whitespace-normalized file(s), "
    f"{hash_changed} hash-reference file(s), {hash_replaced} hash replacement(s)"
)
for rel in HASH_TARGETS:
    if rel in old_hashes:
        print(f"HASH {rel}: {old_hashes[rel]} -> {new_hashes[rel]}")
