#!/usr/bin/env bash
# Workspace: a git repo with a README for a small fictional agency and no docs or brain.
set -euo pipefail

cat > README.md <<'README'
# Northwind Studio

Northwind Studio is a six-person agency in Rotterdam that builds Shopify stores for
direct-to-consumer brands. We started in 2021 and are profitable.

## What we do

- **Store builds:** custom Shopify themes and migrations, fixed price, six to ten weeks.
- **Care plans:** a monthly retainer for fixes, small features and performance work.
- **Audits:** a two-week conversion and speed audit for stores we did not build.

## Team

Mira (founder, sales), Jonas (lead developer), Ana (design), Pieter (project manager),
and two contract developers.

## How we work

Clients are mostly food and apparel brands with 1 to 20 staff. Most come from referrals.
We work in two-week sprints and track tasks in Linear. Files live in Google Drive.
README

export GIT_AUTHOR_DATE="2026-10-01T00:00:00Z" GIT_COMMITTER_DATE="2026-10-01T00:00:00Z"
touch -t 202610010000 README.md
git -c init.defaultBranch=main init -q
git add -A
git -c user.name="Fixture" -c user.email="fixture@example.invalid" -c commit.gpgsign=false \
  commit -q -m "Fixture: Northwind Studio README"
