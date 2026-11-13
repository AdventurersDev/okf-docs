#!/usr/bin/env bash
# Workspace: the brain-repo fixture plus three customer-call assets added after the last log entry,
# one observation backed by two of them (a promotion candidate), one asset that contradicts
# market/audiences.md, and a questions.md whose open question the Initech call answers.
set -euo pipefail
bash "$(dirname "${BASH_SOURCE[0]}")/../fixtures/setup.sh" brain-repo

b=brain
cat > $b/assets/2026-11-03-customer-call-initech.md <<'EOF'
---
type: meeting
x-okfdocs-class: asset
title: Customer call with Initech
description: Call with Initech's IT lead about SSO setup and audit logs.
generated:
  by: okf-docs/1.0.5
  at: 2026-11-03T16:00:00+01:00
sources:
  - resource: pasted in conversation, 2026-11-03
---

# Customer call with Initech

**What it was:** Customer call with Initech's IT lead, to plan their rollout.

## Summary

Initech (240 employees) is rolling Acme out to its operations team. Our solutions engineer confirmed that SAML SSO is live for Okta and Microsoft Entra ID; Google Workspace is not supported yet. Initech's IT lead said the rollout waits until Acme has audit logs for admin actions.

## Decisions

- No clear decisions.

## Actions

- No clear actions.

## Extracted claims

| Claim | Tag | Landed in |
|---|---|---|
| SAML SSO works with Okta and Microsoft Entra ID, not Google Workspace | update | questions.md |
| Initech's rollout waits for admin audit logs | observation | [Customers ask for audit logs before rollout](../observations/2026-11-12-audit-logs-before-rollout.md) |
EOF
cat > $b/assets/2026-11-10-customer-call-umbrella.md <<'EOF'
---
type: meeting
x-okfdocs-class: asset
title: Customer call with Umbrella
description: Call with Umbrella's operations director about audit logs and exports.
generated:
  by: okf-docs/1.0.5
  at: 2026-11-10T15:00:00+01:00
sources:
  - resource: pasted in conversation, 2026-11-10
---

# Customer call with Umbrella

**What it was:** Customer call with Umbrella's operations director, a renewal check-in.

## Summary

Umbrella (180 employees) uses Acme daily for exports. Their operations director said their auditors require a record of who changed workspace settings, so they need audit logs before they expand to a second team.

## Decisions

- No clear decisions.

## Actions

- No clear actions.

## Extracted claims

| Claim | Tag | Landed in |
|---|---|---|
| Umbrella needs audit logs before expanding | observation | [Customers ask for audit logs before rollout](../observations/2026-11-12-audit-logs-before-rollout.md) |
EOF
cat > $b/assets/2026-11-14-customer-call-hooli.md <<'EOF'
---
type: meeting
x-okfdocs-class: asset
title: Customer call with Hooli
description: Call with Hooli's VP of operations about a company-wide rollout.
generated:
  by: okf-docs/1.0.5
  at: 2026-11-14T11:00:00+01:00
sources:
  - resource: pasted in conversation, 2026-11-14
---

# Customer call with Hooli

**What it was:** Customer call with Hooli's VP of operations, to scope a company-wide rollout.

## Summary

Hooli has 3,200 employees and is buying 900 seats for its operations teams across four regions. The VP said Acme is now their standard tool for operations workspaces, and Hooli is not an exception: two other companies in their network with more than 2,000 employees are evaluating Acme.

## Decisions

- No clear decisions.

## Actions

- No clear actions.

## Extracted claims

| Claim | Tag | Landed in |
|---|---|---|
| Hooli (3,200 employees) is buying 900 seats | update | none yet |
EOF
cat > $b/observations/2026-11-12-audit-logs-before-rollout.md <<'EOF'
---
type: customer
x-okfdocs-class: observation
title: Customers ask for audit logs before rollout
description: Initech and Umbrella both said they need audit logs for admin actions before they roll Acme out further.
stale_after: 2027-02-12T00:00:00Z
generated:
  by: okf-docs/1.0.5
  at: 2026-11-12T10:00:00+01:00
sources:
  - id: initech
    resource: ../assets/2026-11-03-customer-call-initech.md
  - id: umbrella
    resource: ../assets/2026-11-10-customer-call-umbrella.md
---

# Customers ask for audit logs before rollout

Two customers, Initech (2026-11-03) and Umbrella (2026-11-10), said they need audit logs of admin actions before they roll Acme out further.[^initech][^umbrella]

## Promotion condition

A second independent source. Two calls now say it.

[^initech]: ../assets/2026-11-03-customer-call-initech.md
[^umbrella]: ../assets/2026-11-10-customer-call-umbrella.md
EOF
cat > $b/questions.md <<'EOF'
---
type: question-list
x-okfdocs-class: tracker
title: Questions
description: Open questions about the company, and where they were answered.
generated:
  by: okf-docs/1.0.5
  at: 2026-10-20T09:00:00+02:00
---

# Questions

## Open

| Area | Question | Why it matters | Asked |
|---|---|---|---|
| Selling | Which identity providers does our SAML SSO support? | Sales needs it to answer admins before rollout (market/audiences.md) | 2026-10-20 |
| Selling | What is our refund policy for annual plans? | Sales and support give different answers | 2026-10-20 |

## Answered

| Area | Question | Answer in | Answered |
|---|---|---|---|
EOF
{
  echo "# Assets"
  echo
  echo "* [Customer call with Hooli](2026-11-14-customer-call-hooli.md) - Call with Hooli's VP of operations about a company-wide rollout."
  echo "* [Customer call with Umbrella](2026-11-10-customer-call-umbrella.md) - Call with Umbrella's operations director about audit logs and exports."
  echo "* [Customer call with Initech](2026-11-03-customer-call-initech.md) - Call with Initech's IT lead about SSO setup and audit logs."
  sed '1,2d' $b/assets/index.md
} > $b/assets/index.new
mv $b/assets/index.new $b/assets/index.md
printf '* [Questions](questions.md) - Open questions about the company, and where they were answered.\n' >> $b/index.md
printf '* [Customers ask for audit logs before rollout](2026-11-12-audit-logs-before-rollout.md) - Initech and Umbrella both said they need audit logs for admin actions before they roll Acme out further.\n' >> $b/observations/index.md

find . -type f -not -path './.git/*' -exec touch -t 202611200000 {} +
export GIT_AUTHOR_DATE="2026-11-20T00:00:00Z" GIT_COMMITTER_DATE="2026-11-20T00:00:00Z"
git add -A
git -c user.name=Fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false commit -qm extra
