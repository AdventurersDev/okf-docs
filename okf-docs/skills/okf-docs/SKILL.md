---
name: okf-docs
description: "Write, check and publish documentation as Open Knowledge Format (OKF) bundles: repo docs and AGENTS.md for coding agents, a company brain for team and business knowledge, and public help, developer and changelog pages with AI bloat removed. Use when the user asks to document something, record a decision, set up or audit docs, add meeting notes or files to company knowledge, wants decisions and actions pulled from a meeting transcript, wants a company brain set up, asks what was decided or how or why something works (in a project with OKF docs, use it for these questions even when the answer seems easy to read from the files: it adds citations and a trust note), wants a README or page debloated, or wants docs published; after engineering work that changed behavior; or with no task for a status menu."
argument-hint: "[init · write · meeting · ask · check · sync · publish] [target]"
allowed-tools:
  - Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/okf.py *)
  - Bash(python ${CLAUDE_SKILL_DIR}/scripts/okf.py *)
  - Bash(py -3 ${CLAUDE_SKILL_DIR}/scripts/okf.py *)
metadata:
  version: "1.0.5"
  okf: "0.3"
---

# OKF Docs

OKF is the format; this skill does the editorial work: get knowledge in, keep it true, get it out. A bundle is a folder of Markdown files with YAML frontmatter that people and agents read without tooling.

## Commands

Type `/okf-docs <command>`, or ask in plain words.

| Command | Module | What it does | Reference |
|---|---|---|---|
| *(none)* | Core | Status and 2–3 suggestions. Never runs a command by itself | [routing.md](reference/routing.md) |
| `init` | Core | Broad first pass: scan, report, ask, plan, build. Re-run to reshape | [init.md](reference/init.md) |
| `write [topic]` | Core | Capture, decide, ingest, co-write | [write.md](reference/write.md) |
| `meeting [file or folder]` | Brain | Take in a meeting transcript or notes: restate it, preview the clear decisions, actions and facts, write after OK | [write.md](reference/write.md), Ingest |
| `ask <question>` | Core | Read-only answer with citations | [ask.md](reference/ask.md) |
| `check [path]` | Core | Format, links, staleness, duplicates, bloat, deletions, review queue | [check.md](reference/check.md) |
| `sync [ref]` | Code | Update docs for code changed since the last sync | [sync.md](reference/sync.md) |
| `publish [target]` | Publish | Public pages from public facts, reader-tested and signed off | [publish.md](reference/publish.md) |

Routing:

- **No argument:** follow [routing](reference/routing.md).
- **A command, or a request that clearly means one** ("document this" → write, "what did we decide about X" → ask, "are the docs current" → check, "turn this into a help page" → publish): read its reference and follow it. If two fit, ask once.
- **"Debloat this" on any Markdown file**, in a bundle or not: apply [writing](reference/writing.md) to that file. No bundle or init needed.
- **At the end of a task that changed behavior in code**, where the Code module is on: update the docs that cite the changed files and say so in one line. Propose new docs and decisions in one line instead of writing them ([write](reference/write.md), "When to write"). Skip refactors, formatting and test changes that change no behavior.
- **When the user corrects how something works or states a convention**, record it ([write](reference/write.md), "Capture"): fix the wrong fact at once, propose the rest in one line.
- **"Review the brain"** → check, brain review ([check](reference/check.md)).
- **Actions to tickets** ("put these actions in Linear", "sync the open actions"): follow write.md, Tickets. With `brain.tickets` unset, ask which system and target, and offer to save them in the config.
- **A meeting transcript or notes**, given with `meeting`, `write`, `check meeting` or in plain words ("add this call to the brain"): follow write.md, Ingest, "Meetings and transcripts". No file or text given: ask for it. A folder or several files: "Several meetings at once". No brain bundle: say so in one line and offer `/okf-docs init` with the Brain module.

## Setup

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/okf.py context` once per session from the user's project. It reports the config, enabled modules, bundles, open findings, `NOW` (the timestamp to write) and `ACTOR` (who to write as), then directives. Follow the directives. Run it again only after init changes the config.

Every script command is `python3 ${CLAUDE_SKILL_DIR}/scripts/okf.py <command>`; `--help` lists them. On Windows, `python3` is often missing or opens a Microsoft Store prompt: if it fails, try `python`, then `py -3`, and use whichever works for every script command. Quote the script path if it contains spaces. Run each script command on its own in that form, with `--project <path>` instead of `cd <path> && …`: permission rules match the plain form and may refuse compound commands. A refused shell command doesn't mean the script is blocked; try the script commands before you skip them. If no Python works, or the script fails, say so in one line, read `.okf/config.yaml` yourself, and carry on without script checks.

## Modules

Core is always on. Init switches the others on, and the context output lists them. Read a module's references only when it is on. If the user asks for a command from a module that is off, say so and offer `/okf-docs init` to switch it on.

| Module | Adds | Read |
|---|---|---|
| Core | `init`, `write`, `ask`, `check` on any OKF bundle | [format](reference/format.md), [lifecycle](reference/lifecycle.md), [writing](reference/writing.md) |
| Code | Repo `docs/` bundle, `AGENTS.md`, `sync` | [kinds/docs](reference/kinds/docs.md) |
| Brain | Company bundle: meetings and files as assets, strict decision and action extraction, ticket sync for actions, company interview, trackers, sensitive-content rules | [kinds/brain](reference/kinds/brain.md) |
| Publish | `publish`: help center, developer docs, changelog, team updates | [kinds/site](reference/kinds/site.md) |

## Rules for every command

1. **One home per fact.** A fact lives in one bundle file. Pages, updates, changelogs and AGENTS.md cite it; they never become a second source of truth.
2. **Code docs or brain.** If it would change when the code changes, it belongs in the repo's docs bundle. If it would survive a rewrite (purpose, audience, strategy, customers, business decisions, how the team works), it belongs in the brain. When both apply, write two files that link to each other and share no prose.
3. **Understand before you write what people tell you** ([write](reference/write.md), "Understand first"): restate it, ask about what is unclear, write only what is clear or confirmed.
4. **Never invent provenance.** `sources` lists only what you read or were told, with `author` for who stated it. Unknown origin: say so in the body and leave `sources` out. Never add a `human:` verification the person didn't give, or an id they didn't confirm.
5. **Write per [writing](reference/writing.md).** Every sentence carries a fact or an instruction.
6. **Format per [format](reference/format.md).** Timestamps from `NOW`, actors from `ACTOR`, relative links unless config says `links: rooted`.
7. **Change, replace and delete per [lifecycle](reference/lifecycle.md).** Propose deletions as a list; delete only after approval.
8. **Log structural changes** (new, moved, deprecated or deleted files; decisions) with `okf.py log <bundle> <Kind> "<what>"`, where Kind is Creation, Update, Deprecation, Deletion, Decision or Review.
9. **Check your work:** after writing, run `okf.py check <paths>`, and `okf.py index --write` if you added, moved or deleted files. Fix what they report before you finish.
10. **Report in one line per bundle** what changed and where.
