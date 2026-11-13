# Presets: brain

Starting layouts for a company brain ([kinds/brain](../reference/kinds/brain.md)). Create a folder when its first file has content. Files that need facts only people have, such as strategy and principles, start as drafts of what the user said, never as guesses.

## company

A company's or business unit's knowledge, in a `brain/` bundle, usually its own repository. Never at the same path as the repo docs or inside them: in a code repository it sits next to `docs/`, as `brain/`. Check reports `bundle-overlap` otherwise.

| Folder | First files | `x-okfdocs-class` |
|---|---|---|
| `company/` | `organization.md` (what the company is, its functions), `principles.md`, `strategy.md`, `glossary.md` (terms, acronyms, codenames), `tools.md` (tools per job, where documents live), `priorities.md` (this quarter; `stale_after` three months) | canonical |
| `operations/` | `sales.md`, `delivery.md`, `support.md`: how the company sells, delivers and supports; one process per file | canonical (type process) |
| `products/<name>/` | `<name>.md`: purpose, audience, problem, positioning, pricing model; links to the repo docs | canonical |
| `market/` | `audiences.md`, `problems.md`, `competitors.md`; `clients/<name>.md` per key client | canonical, reference for competitors |
| `people/` | `team.md`: roles, who owns which area, who decides what (decision rights) | canonical (type function) |
| `actions.md`, `questions.md` | Living lists at the root; `actions.md` only with `brain.actions: track` | tracker |
| `decisions/` | Business decisions, `NNN-short-title.md` | decision |
| `observations/` | Findings not yet accepted, `YYYY-MM-DD-slug.md`, each with `stale_after` | observation |
| `assets/` | Metadata for meetings, transcripts, emails and documents; raw files in `assets/files/` | asset |

## handbook

How the team works: `people/` inside the brain, or a separate `handbook/` bundle (`kind: brain`) when it has other readers or owners than the brain.

| File | `type` | Holds |
|---|---|---|
| `team.md` | function | Roles, responsibilities and handles. No phone numbers or home addresses |
| `rituals.md` | process | Recurring meetings: purpose, cadence, owner |
| `how-we-work.md` | policy | Working agreements: reviews, decisions, channels, hours |
| `onboarding.md` | process | First-week steps and who to ask |
| `tools.md` | process | Each tool, what it is for, who administers it, how to get access. In a company brain with `company/tools.md`, keep one of the two |

All handbook files are `x-okfdocs-class: canonical`. Personnel and health matters never go in the handbook.
