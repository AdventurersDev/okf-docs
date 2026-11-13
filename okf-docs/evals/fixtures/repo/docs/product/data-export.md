---
type: concept
title: Data export
description: Export a workspace as CSV or JSON; runs as a background job with a 500 MB limit.
tags: [export, jobs]
specificity: specific
visibility: public
generated:
  by: okf-docs/0.9.1
  at: 2026-11-01T10:00:00+01:00
verified:
  - by: human:alex
    at: 2026-11-02T09:00:00+01:00
sources:
  - id: job
    resource: ../../src/export/job.ts
  - id: d002
    resource: ../decisions/002-json-export.md
---

# Data export

Workspace owners export records as CSV or JSON from Settings → Export, for the whole workspace or one project at a time.[^job]

## Behavior

- The export runs as a background job and emails a download link when it finishes.
- JSON is the default format since [decision 002](../decisions/002-json-export.md).[^d002]

## Constraints

- Exports over 500 MB fail with `EXPORT_TOO_LARGE`. Exporting one project at a time keeps each export smaller.

## Related

- [Architecture](../system/architecture.md)

[^job]: ../../src/export/job.ts
[^d002]: ../decisions/002-json-export.md
