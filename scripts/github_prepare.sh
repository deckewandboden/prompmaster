#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
python3 scripts/github_preflight.py
if [[ ! -d .git ]]; then
  git init
  git branch -M main
fi
if ! git config user.name >/dev/null 2>&1; then
  git config user.name "${PM_GIT_AUTHOR_NAME:-PromptMaster Build}"
fi
if ! git config user.email >/dev/null 2>&1; then
  git config user.email "${PM_GIT_AUTHOR_EMAIL:-promptmaster-build@local.invalid}"
fi
git add -A
if git diff --cached --quiet; then
  echo "Git-Arbeitsbaum ist bereits für den Erstimport vorbereitet; keine neuen Änderungen."
else
  git commit -m "PromptMaster Commercial GitHub RC13"
fi
if ! git show-ref --verify --quiet refs/heads/staging; then
  git branch staging main
fi
printf '\nGitHub-ready. Branches: main + staging.\n'
printf 'Nächster Schritt: privates leeres Repository als origin setzen und beide Branches pushen.\n'
