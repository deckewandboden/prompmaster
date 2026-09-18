#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TSV = ROOT / 'FILE_MANIFEST.tsv'
AUDIT_TSV = ROOT / 'FILE_MANIFEST_AUDIT.tsv'
JSON_OUT = ROOT / 'MANIFEST.json'
MD = ROOT / 'docs' / 'COMPLETE_FILE_INVENTORY.md'

EXCLUDED = {
    TSV.resolve(),
    AUDIT_TSV.resolve(),
    JSON_OUT.resolve(),
    MD.resolve(),
}

# Diese Build-Artefakte werden durch andere Validatoren geprüft.
VOLATILE_PREFIXES = (
    'marketing/dist/',
)

# Nur echte Binärdateien werden zusätzlich bytegenau gegen das Manifest
# geprüft. Textdateien werden von Git selbst versioniert und dürfen wegen
# LF/CRLF-Unterschieden zwischen Windows und Linux nicht bytegenau geprüft
# werden.
BINARY_SUFFIXES = {
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.webp',
    '.ico',
    '.pdf',
    '.glb',
    '.gltf',
    '.woff',
    '.woff2',
    '.ttf',
    '.eot',
    '.mp3',
    '.mp4',
    '.wav',
    '.avi',
    '.mov',
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open('rb') as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b'',
        ):
            digest.update(chunk)

    return digest.hexdigest()


def volatile(rel: str) -> bool:
    return any(
        rel.startswith(prefix)
        for prefix in VOLATILE_PREFIXES
    )


def get_git_tracked_files() -> list[str]:
    try:
        result = subprocess.run(
            ['git', 'ls-files', '-z'],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            'MANIFEST VALIDATION FAIL: Git tracked files could not be determined'
        ) from exc

    files: list[str] = []

    for raw in result.stdout.split(b'\0'):
        if not raw:
            continue

        files.append(
            raw.decode(
                'utf-8',
                errors='surrogateescape',
            )
        )

    return files


# ---------------------------------------------------------------------------
# Manifest laden
# ---------------------------------------------------------------------------

if not TSV.exists():
    raise SystemExit(
        'MANIFEST VALIDATION FAIL: FILE_MANIFEST.tsv missing'
    )

expected: dict[str, tuple[int, str, str]] = {}
manifest_sources = [TSV]
if AUDIT_TSV.exists():
    manifest_sources.append(AUDIT_TSV)

for manifest_path in manifest_sources:
    for line in manifest_path.read_text(encoding='utf-8').splitlines()[1:]:
        if not line.strip():
            continue

        try:
            rel, size, digest, role = line.split('\t', 3)
        except ValueError as exc:
            raise SystemExit(
                f'MANIFEST VALIDATION FAIL: malformed manifest row in '
                f'{manifest_path.name}: {line}'
            ) from exc

        if rel in expected:
            raise SystemExit(
                'MANIFEST VALIDATION FAIL: duplicate manifest path across inventories: '
                f'{rel}'
            )

        expected[rel] = (
            int(size),
            digest,
            role,
        )


# ---------------------------------------------------------------------------
# Git-tracked Dateien validieren
# ---------------------------------------------------------------------------

tracked_files = get_git_tracked_files()

checked = 0
binary_checked = 0

for rel in sorted(tracked_files):

    path = ROOT / rel

    if path.resolve() in EXCLUDED:
        continue

    if volatile(rel):
        continue

    if not path.exists():
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: tracked file missing: {rel}'
        )

    if not path.is_file():
        continue

    manifest_row = expected.get(rel)

    if manifest_row is None:
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: tracked file not listed in manifest: {rel}'
        )

    expected_size, expected_digest, _role = manifest_row

    # Textdateien:
    # Git ist die maßgebliche Integritäts-/Versionskontrolle.
    # Kein bytegenauer Vergleich, weil CRLF/LF zwischen Windows und Linux
    # unterschiedlich sein kann.
    #
    # Binärdateien:
    # weiterhin bytegenaue Prüfung.
    if path.suffix.lower() in BINARY_SUFFIXES:

        actual_size = path.stat().st_size

        if actual_size != expected_size:
            raise SystemExit(
                'MANIFEST VALIDATION FAIL: '
                f'binary size drift {rel}'
            )

        actual_digest = sha256(path)

        if actual_digest != expected_digest:
            raise SystemExit(
                'MANIFEST VALIDATION FAIL: '
                f'binary hash drift {rel}'
            )

        binary_checked += 1

    checked += 1


# ---------------------------------------------------------------------------
# Alte lokale Manifest-Einträge
#
# Diese können aus Backups/ZIPs stammen, die lokal vorhanden waren,
# aber nie Git-tracked waren.
# ---------------------------------------------------------------------------

tracked_set = set(tracked_files)

obsolete = sorted(
    rel
    for rel in expected
    if rel not in tracked_set
    and not volatile(rel)
)

if obsolete:
    print(
        f'MANIFEST NOTICE: '
        f'{len(obsolete)} non-Git manifest entries ignored'
    )


print(
    'MANIFEST VALIDATION OK: '
    f'{checked} Git-tracked files inventoried; '
    f'{binary_checked} binary files byte-validated; '
    f'{len(manifest_sources)} inventory file(s) loaded'
)
