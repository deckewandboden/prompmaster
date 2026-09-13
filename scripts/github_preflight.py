#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    print(
        '+',
        ' '.join(args),
        flush=True,
    )

    subprocess.run(
        args,
        cwd=ROOT,
        check=True,
    )


# ---------------------------------------------------------------------------
# Repository/static validation
# ---------------------------------------------------------------------------

checks = [
    ('python', 'scripts/validate_runtime_config.py'),
    ('python', 'scripts/test_runtime_config.py'),
    (
        'python',
        'scripts/validate_python_syntax.py',
    ),
    (
        'python',
        'scripts/validate_prompt_assets.py',
    ),
    (
        'python',
        'scripts/validate_prompt_domain.py',
    ),
    (
        'python',
        'scripts/validate_runtime_catalog.py',
    ),
    (
        'python',
        'scripts/validate_marketing.py',
    ),
    (
        'python',
        'scripts/validate_static.py',
    ),
    (
        'python',
        'scripts/validate_repo.py',
    ),
    (
        'python',
        'scripts/validate_manifest.py',
    ),
]

for command in checks:
    run(*command)


# ---------------------------------------------------------------------------
# Shell syntax validation
# ---------------------------------------------------------------------------

shell_scripts = (
    sorted(
        (ROOT / 'scripts').glob('*.sh')
    )
    + sorted(
        (ROOT / 'backup').glob('*.sh')
    )
)

for path in shell_scripts:
    run(
        'bash',
        '-n',
        str(path),
    )


# ---------------------------------------------------------------------------
# Git repository hygiene
# ---------------------------------------------------------------------------

if (ROOT / '.git').exists():

    run(
        'git',
        'diff',
        '--check',
    )

    proc = subprocess.run(
        [
            'git',
            'status',
            '--porcelain',
        ],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    disallowed: list[str] = []

    for line in proc.stdout.splitlines():

        if len(line) < 4:
            continue

        rel = line[3:].strip()

        # Real .env files must never become repository artifacts.
        if (
            rel == '.env'
            or (
                rel.startswith('.env.')
                and rel != '.env.example'
            )
        ):
            disallowed.append(rel)

        # Python cache files must never be committed/generated as part of
        # repository source.
        if (
            '__pycache__' in rel
            or rel.endswith('.pyc')
        ):
            disallowed.append(rel)

    if disallowed:
        raise SystemExit(
            'GITHUB PREFLIGHT FAIL: '
            'untracked/generated secret/cache files: '
            + ', '.join(sorted(set(disallowed)))
        )


print(
    'GITHUB PREFLIGHT OK: '
    'static/code/assets/runtime-catalog/repository guards passed'
)

print(
    'NOTE: generated marketing/dist output is validated by the dedicated '
    'marketing and browser checks rather than static manifest hashes.'
)

print(
    'NOTE: Django/PostgreSQL/Docker runtime validation still requires '
    'a Docker-capable host or GitHub Actions.'
)
