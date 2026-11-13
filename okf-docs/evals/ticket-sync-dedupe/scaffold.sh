#!/usr/bin/env bash
# Workspace: the brain-repo fixture with ticket sync to Linear switched on, an actions.md whose pilot-contract
# action already has ticket ENG-412, and the earlier meeting that action came from. No Linear connector.
set -euo pipefail
bash "$(dirname "${BASH_SOURCE[0]}")/../fixtures/setup.sh" brain-repo
cat >> .okf/config.yaml <<'EOF'
brain:
  actions: track
  names: team
  tickets:
    system: linear
    target: ENG
EOF
cat > brain/assets/2026-11-05-initech-pilot-call.md <<'EOF'
---
type: meeting
x-okfdocs-class: asset
title: Initech pilot call
description: Call with Initech's IT lead about starting a 60-day pilot.
generated:
  by: okf-docs/1.0.5
  at: 2026-11-05T15:00:00Z
sources:
  - id: notes
    resource: pasted in conversation, 2026-11-05
---

# Initech pilot call

| Property | Value |
|---|---|
| Kind | meeting |
| Date | 2026-11-05 |
| Origin | Initech IT lead; Sam (Acme sales) |
| File | not stored |
| Sensitive content | none |

**What it was:** customer call with Initech's IT lead and Sam (sales) about a pilot.

## Summary

Initech wants a 60-day pilot for its ops team. Sam will send the pilot contract.

## Decisions

- No clear decisions.

## Actions

- Sam: send Initech the pilot contract, due 2026-11-14 ([ENG-412](https://linear.app/acme/issue/ENG-412))

## Extracted claims

| Claim | Tag | Landed in |
|---|---|---|
| Initech wants a 60-day pilot | ignore | - |
EOF
cat > brain/actions.md <<'EOF'
---
type: action-list
title: Actions
description: Open and done actions from meetings.
x-okfdocs-class: tracker
generated:
  by: okf-docs/1.0.5
  at: 2026-11-05T15:00:00Z
---

# Actions

## Open

| Owner | Action | Ticket | Due | From | Added |
|---|---|---|---|---|---|
| Sam | Send Initech the pilot contract | [ENG-412](https://linear.app/acme/issue/ENG-412) | 2026-11-14 | [Initech pilot call](assets/2026-11-05-initech-pilot-call.md) | 2026-11-05 |

## Done

| Owner | Action | Ticket | Due | From | Added | Done |
|---|---|---|---|---|---|---|
EOF
