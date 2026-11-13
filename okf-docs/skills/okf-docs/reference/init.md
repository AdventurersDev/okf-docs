# init

A broad first pass, a short conversation, then a plan the user approves. Everyday work is iterative and never needs init again. Re-run it to reshape: add a module or bundle, or change the layout.

## 1. Scan before asking

Read only; write nothing yet.

| Look at | What to find |
|---|---|
| Project shape | Languages, package manifests, workspaces, apps versus libraries versus services, deploy config, API specs (OpenAPI, GraphQL, protobuf), database schemas and migrations |
| Existing docs | READMEs, `docs/`, `CHANGELOG*`, `CONTRIBUTING*`, ADR folders, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, docs-site config (`mkdocs.yml`, `docusaurus.config.*`, `astro.config.*` with Starlight, `.vitepress/`) |
| OKF bundles | The ones the context output lists, and a company brain, here or in a sibling checkout |
| Legacy state from the v3 skills | `.agent/okf/` (`jobs.json`, `bootstrap-manifest.json`) and v3 frontmatter. The context output flags both |
| Git | Whether it's a repo, how much history it has, the default branch |

Measure what exists: `okf.py check --json` on each bundle and `okf.py lint` on the top-level docs. Treat every inference as a hypothesis to confirm.

## 2. Report

Keep it short: what exists and its state (OKF errors, stale files, bloat); what each audience lacks (agents, team, company, public readers); and the preset you think fits (presets/docs.md, brain.md, site.md), with the evidence.

## 3. Ask only about the gaps

At most three questions per round, with AskUserQuestion when available and the recommended option first. Confirm inferences instead of asking open questions: "This looks like a service with a public REST API. Right?" Typical gaps:

| Gap | Ask about |
|---|---|
| Modules | Agents and team (Code), company knowledge (Brain), public pages (Publish) |
| Brain location | A path or a repository URL, when Brain is on or the repo docs should link to it. Its own repository is best; in the same repository it gets its own folder next to `docs/`, never `docs/` itself or a folder inside it |
| Who verifies | The id `okf.py now` prints. To change it, each person runs `git config --global okf.actor <id>`; it never goes in the shared config |
| Publish | Which targets (help center, developer docs, changelog, team updates) and which site tool. Reader and tone wait until the first publish, which asks once per site |
| Edit hook | Whether to turn it on (`hooks.edits`). After an edit, it reminds the agent once about docs that cite the edited code, and reports format problems in edited docs. Recommend it with the Code module. The session-start hook is on by default and needs no question |

Stop asking when the answers would no longer change the plan.

## 4. Propose a plan and wait

List:

- the config to write;
- folders, only those that will hold a file now;
- first files, each with its title and the sources it will cite, unreviewed until the user confirms them;
- migrations: format upgrades and content to move from old docs into the bundle;
- proposed deletions or merges of existing docs, per lifecycle.md.

Ask for an OK. If the plan changes, show the new one and confirm again.

## 5. Build

1. Write `.okf/config.yaml` from templates/config.yaml. Tell the user to commit it. A brain in another repository goes under `related.brain`: its `url` for links and, when it's checked out on this machine, its `path` relative to this repo. Run `okf.py context` and confirm the `RELATED` line says `(found)`.
2. Create each bundle: root `index.md` with `okf_version: "0.2"`, `log.md`, and the first files from templates, each with sources and `credibility`, and no `verified` entry.
3. Code module: write or update `AGENTS.md` from templates/agents-md.md. If a `CLAUDE.md` exists, Claude Code reads it instead of `AGENTS.md`, so propose adding the line `@AGENTS.md` to it rather than duplicating content.
4. Carry out approved migrations: move facts from old docs into bundle files and leave READMEs as short entry points that link to the docs. Run `okf.py upgrade` for v3 files.
5. Keep what the user told you. Settings live in the config. Facts they stated (what the product is, who uses it, a convention) go into the first files that cover them, with the body note "Stated by <ACTOR> during init on <date>"; that's their origin, not a review, so it gets no `verified` entry. A stated choice with a reason someone will need later becomes a decision.
6. Run `okf.py index --write`, `okf.py log <bundle> Initialization "<what was set up, and the choices the user made>"` and `okf.py check`.
7. Report what was created, the review queue (the files to verify), and two or three next steps.

Never overwrite an existing file without showing the change first. Never delete during init unless the approved plan listed it.

## Re-running init

Read the config, scan again, and report only what changed: new packages, new docs, modules worth adding. Ask only about those and propose a delta plan. A small layout change during normal work, such as one new folder, doesn't need init: ask in one line and do it.
