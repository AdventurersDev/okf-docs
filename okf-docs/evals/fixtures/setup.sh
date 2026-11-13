#!/usr/bin/env bash
# Seeds an eval run's empty workspace with one fixture project, committed and dated 2026-10-01,
# so staleness checks see the same times on every run: commit times where git runs, file times
# where it doesn't (macOS sandboxes can block git). Each case's scaffold.sh calls it.
set -euo pipefail

name="${1:?usage: setup.sh <fixture>}"
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$name"
if [ ! -d "$src" ]; then
  echo "setup.sh: no fixture named '$name' next to setup.sh" >&2
  exit 1
fi

cp -R "$src/." .
find . -type f -exec touch -t 202610010000 {} +

export GIT_AUTHOR_DATE="2026-10-01T00:00:00Z" GIT_COMMITTER_DATE="2026-10-01T00:00:00Z"
git -c init.defaultBranch=main init -q
git add -A
git -c user.name="Fixture" -c user.email="fixture@example.invalid" -c commit.gpgsign=false \
  commit -q -m "Fixture: $name"
