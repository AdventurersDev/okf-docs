---
type: decision
title: JSON as the default export format
description: JSON became the default export format because customers import exports into other tools.
x-okfdocs-supersedes: 001-csv-first.md
generated:
  by: okf-docs/1.0.5
  at: 2026-10-20T15:30:00+02:00
verified:
  - by: human:alex
    at: 2026-10-21T09:00:00+02:00
---

# JSON as the default export format

## Context

Most exports were imported into other tools, and CSV lost nested fields.

## Decision

JSON is the default export format. CSV stays available.

## Affected

- [Data export](../product/data-export.md)
