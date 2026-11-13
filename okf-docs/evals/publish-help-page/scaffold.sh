#!/usr/bin/env bash
# Workspace: the repo fixture plus a voice.md for its help center, committed.
set -euo pipefail
bash "$(dirname "${BASH_SOURCE[0]}")/../fixtures/setup.sh" repo
cat > help/voice.md <<'EOF'
---
type: voice
title: Voice for the help center
description: Workspace owners reading the help center; plain and friendly; en-US.
generated:
  by: okf-docs/0.9.1
  at: 2026-10-01T00:00:00+00:00
---

# Voice for the help center

## Reader

Workspace owners who manage their team's data. They aren't developers.

## Tone

Plain and friendly. Address the reader as "you".

## Language

US English. Dates as November 10, 2026.

## Brand voice

None.
EOF
touch -t 202610010000 help/voice.md
GIT_AUTHOR_DATE="2026-10-01T00:00:00Z" GIT_COMMITTER_DATE="2026-10-01T00:00:00Z" \
  git -c user.name="Fixture" -c user.email="fixture@example.invalid" -c commit.gpgsign=false \
  add help/voice.md
GIT_AUTHOR_DATE="2026-10-01T00:00:00Z" GIT_COMMITTER_DATE="2026-10-01T00:00:00Z" \
  git -c user.name="Fixture" -c user.email="fixture@example.invalid" -c commit.gpgsign=false \
  commit -qm "Add the help center voice"
