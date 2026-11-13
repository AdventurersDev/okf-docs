# Kind: docs (Code module)

A repo's implementation truth, in `docs/` or the path in config, plus `AGENTS.md` at the repo root.

## What belongs here

Feature behavior, states, limits and invariants; product scope decisions; designs and UX flows; architecture; APIs, webhooks and integrations; schemas and data models; code conventions; infrastructure and environments; security as implemented; runbooks; technical decisions. Purpose, audience, strategy and customers go to the brain.

## Layout

Folders follow the question a reader asks. Create only folders that hold a file; a small repo stays flat. The preset (presets/docs.md) sets the starting folders.

```
docs/
├── index.md
├── log.md
├── product/       what it does: features, behavior, limits, designs
├── system/        how it's built: architecture, api/, schema/, conventions/
├── operations/    how we run it: runbooks, environments, infrastructure
├── security/      how it's kept safe: controls, threat models, data handling
└── decisions/     why it's this way: NNN-short-title.md
```

## Types

| `type` | For | Template |
|---|---|---|
| `concept` | A feature or behavior | concept |
| `design` | A UX flow or component design | design |
| `api` | An endpoint, webhook, event or integration | api |
| `schema` | A table, model, type or file format | schema |
| `convention` | A rule the code must follow | convention |
| `security` | A control, threat model or data-handling rule | security |
| `runbook` | How to deploy, recover or operate | runbook |
| `decision` | Why it's this way | decision |

## Sources

Cite the code a doc describes with paths relative to the doc, such as `../../src/export/job.ts`. Sync and the edit hook use these paths to find the docs a code change affects, so cite the files that define the behavior, not every file you opened.

## AGENTS.md

The file coding agents read first, at the repo root. Claude Code reads it when the repo has no `CLAUDE.md`. When a `CLAUDE.md` exists, add the line `@AGENTS.md` to it (ask first) instead of duplicating content.

- Keep it under about 100 lines: what the repo is (one line, plus a link to the brain's product file if there is one), exact commands to build, test and run, where things live, the conventions agents must follow, and which docs to read before changing what.
- Point, don't copy: link docs files instead of restating them.
- It isn't an OKF concept and has no frontmatter.
