# OKF Docs

A Claude Code plugin that writes, checks and publishes documentation as [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (OKF v0.2) bundles: folders of Markdown files with YAML frontmatter that people and agents read without tooling.

## Install

```
/plugin marketplace add AdventurersDev/okf-docs
/plugin install okf-docs@waybound
```

The checks need Python 3.8 or later, standard library only; without it the skill works minus the checks. On Windows, install Python from python.org: the `python3` that opens the Microsoft Store doesn't work. The plugin tries `python3`, `python` and `py -3`.

To install a local copy, such as a clone of this repository, run `/plugin marketplace add <folder>` instead. [TESTING.md](TESTING.md) lists what to check.

## Start

```
/okf-docs init
```

Init scans the repo and its docs, reports what it found, asks at most three questions per round, and proposes a plan. It writes nothing until you approve. After that, ask in plain words ("record this decision", "what did we decide about exports?") or use a command.

| Command | What it does |
|---|---|
| `/okf-docs` | Status and two or three suggestions. Runs nothing |
| `/okf-docs init` | Scan, questions, plan, build. Re-run it to add a module or change the layout |
| `/okf-docs write [topic]` | Captures knowledge, records decisions, ingests meetings and files, co-writes long documents |
| `/okf-docs ask <question>` | Answers from the docs with citations and a trust note. Read-only |
| `/okf-docs check [path]` | Format, links, staleness, duplicates, bloat, deletion candidates, review queue |
| `/okf-docs sync [ref]` | Updates docs for code changed since the last sync |
| `/okf-docs publish [target]` | Public pages from public facts, in the site's voice, signed off by a person. A site's first page starts with up to three questions on reader, tone and language |

"Debloat this" works on any Markdown file, in a bundle or not. If another skill is also called `okf-docs`, use `/okf-docs:okf-docs`.

## Modules

Core is always on. Init switches on the others, so a team that only wants repo docs never sees the brain or publishing.

| Module | For | Adds |
|---|---|---|
| Core | Everyone | init, write, ask and check on any OKF bundle |
| Code | Coding agents and the team | A `docs/` bundle in the repo, `AGENTS.md`, decisions, runbooks, sync |
| Brain | The company | A brain bundle: products, audiences, strategy, customers; meetings and files kept as sources |
| Publish | The public | Help center, developer docs (Diátaxis), changelog, team updates |

## What it writes

```
your-repo/
├── .okf/config.yaml     modules, bundles, decay, hooks
├── AGENTS.md            commands, layout, rules, which docs to read
└── docs/
    ├── index.md         generated listing
    ├── log.md           change history
    ├── product/  system/  operations/  security/
    └── decisions/       NNN-short-title.md
```

A doc:

```markdown
---
type: concept
title: Data export
description: Export a workspace as CSV or JSON; runs as a background job, 500 MB limit.
credibility: reported
generated:
  by: okf-docs/0.9.1
  at: 2026-11-12T14:03:22+01:00
verified:
  - by: human:alex
    at: 2026-11-12T16:40:00+01:00
sources:
  - id: job
    resource: ../../src/export/job.ts
---

# Data export

Exports over 500 MB fail with `EXPORT_TOO_LARGE`.[^job]

[^job]: src/export/job.ts
```

## How docs stay true

| Rule | How it works |
|---|---|
| One home per fact | Pages, changelogs and `AGENTS.md` cite bundle files instead of copying them |
| Sources | A doc lists the code it describes. When that code changes after the doc was checked, check and sync flag it, by git commit times or, outside git, file times |
| Trust | A doc is unverified until a person adds a `verified` entry. `credibility` records where it came from: `reported` (a source or person stated it) or `inferred` (Claude concluded it). Ask ranks reviewed, then reported, then inferred |
| Decay | A doc's weight halves every half-life since it was verified: 12 months by default, 3 for observations, 6 for runbooks. Decisions and records of a moment don't decay. Ask ranks files by scope, trust, specificity and decay |
| Restraint | Docs change once per task, not after each edit. Changed facts are updated; new files are proposed unless you ask for them. Fixes, refactors and tests get no docs |
| Deletion | A replaced file is deleted, not kept beside its replacement; an overturned decision is kept and marked. Deletions are proposed as a list, done after approval, and logged |

Bundles are valid OKF v0.2. The plugin adds frontmatter keys that other OKF tools ignore (`scope`, `specificity`, `credibility`, `class`, `visibility`, `supersedes`, `superseded_by`). It writes `status` only as `deprecated`; review lives in `verified`, not in a `draft` label, and check labels each finding as OKF (breaks the spec), house (plugin convention) or content. The plugin is not affiliated with Google or the OKF project.

## Configuration

Init writes `.okf/config.yaml`; [templates/config.yaml](okf-docs/skills/okf-docs/templates/config.yaml) lists every key.

- **Session hook**, on by default: at session start, tells Claude the docs exist and when to use them. About 60 words, and only in projects with a config. `hooks.session: false` turns it off.
- **Edit hook**, off by default: after Claude edits a file that docs cite, reminds Claude once per session to update them at the end of the task, and reports format problems in docs Claude edits. `hooks.edits: true` turns it on.
- **Your id** in `verified` entries: `OKF_ACTOR`, or `git config --global okf.actor <id>`, or else your git `user.name`.
- **CI:** `python3 okf-docs/skills/okf-docs/scripts/okf.py check --project <repo>` exits with 1 on OKF errors. Pin a commit, not `main`.

Hooks run only in Claude Code. In claude.ai, the Claude apps or other agents, the skill works without them.

## Moving from the okf-docs and okf-company-brain skills

One plugin replaces both skills: the Code module does what okf-docs did, the Brain module what okf-company-brain did.

1. Turn the old skills off. If you added them on claude.ai, turn them off there, or Claude Code syncs them back.
2. Commit your open changes, then run `/okf-docs check`. It finds files in the old format and offers an upgrade that shows every change first.
3. Approve the plan. It converts timestamps, actors, sources and links; keeps `credibility: reported` and `inferred`; and drops `credibility: verified` only where a person's `verified` entry backs it.
4. It also lists what the upgrade won't do on its own: pages kept in a folder's `index.md` (moved to their own file, links repointed), and old rules in the project, such as copies of the skills in `.claude/skills/` or `CLAUDE.md` lines saying "no `status` field". Those change only after you approve them.

While an old skill is on, Claude may pick it for plain-language requests and follow its rules.

## Contributing

Tests, evals and their costs are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
