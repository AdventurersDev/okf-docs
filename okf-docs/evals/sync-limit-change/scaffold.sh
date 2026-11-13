#!/usr/bin/env bash
# Workspace: the repo fixture, then a commit that raises the export limit from 500 MB to 1 GB.
# The doc that states the limit was verified on 2026-11-02; the change is dated 2026-11-10.
set -euo pipefail
bash "$(dirname "${BASH_SOURCE[0]}")/../fixtures/setup.sh" repo
sed -i.bak "s/500 \* 1024 \* 1024/1024 * 1024 * 1024/" src/export/job.ts && rm src/export/job.ts.bak
touch -t 202611100000 src/export/job.ts
GIT_AUTHOR_DATE="2026-11-10T00:00:00Z" GIT_COMMITTER_DATE="2026-11-10T00:00:00Z" \
  git -c user.name="Fixture" -c user.email="fixture@example.invalid" -c commit.gpgsign=false \
  commit -qam "Raise the export limit to 1 GB"
