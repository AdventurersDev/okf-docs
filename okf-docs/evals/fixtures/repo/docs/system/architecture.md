---
type: design
title: Architecture
description: API server, job worker and Postgres; exports run in the worker.
generated:
  by: okf-docs/1.0.5
  at: 2026-11-01T10:00:00+01:00
sources:
  - resource: ../../src/export/job.ts
---

# Architecture

```mermaid
flowchart LR
  client --> api[API server] --> db[(Postgres)]
  api --> worker[Job worker] --> db
```

## Components

- The API server handles requests and queues jobs.
- The job worker runs exports and emails the download link.
