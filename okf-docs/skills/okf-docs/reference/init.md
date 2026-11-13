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

Init exists to understand how the team works, so it asks more than other commands do: ask about every gap whose answer changes the plan. Ask in rounds of up to four questions (one AskUserQuestion call when available), grouped by topic, with the recommended option first; take as many rounds as needed. Confirm inferences instead of asking open questions: "This looks like a service with a public REST API. Right?" Typical gaps:

| Gap | Ask about |
|---|---|
| Modules | Agents and team (Code), company knowledge (Brain), public pages (Publish) |
| Brain location | A path or a repository URL, when Brain is on or the repo docs should link to it. Its own repository is best; in the same repository it gets its own folder next to `docs/`, never `docs/` itself or a folder inside it |
| Brain settings | Recommended option first: `brain.actions` (`report`, `track` or `off`: what to do with action items found in meetings), `brain.names` (`team`, `roles` or `all`: how people are named in knowledge files) and, unless actions are `off`, `brain.tickets`: whether to also create tickets for meeting actions, and in which system. Offer the ticket systems this session has connectors for, then other systems the user names, then "No ticket sync"; recommend a connected one if there is one. Set `brain.tickets` only from the user's answer, never from the connectors alone. With a system, ask the target (team, project or repository); for GitHub, suggest this repository's remote. All are in templates/config.yaml |
| Publish | Which targets (help center, developer docs, changelog, team updates) and which site tool. Reader and tone wait until the first publish, which asks once per site |
| Edit hook | Whether to turn it on (`hooks.edits`). After an edit, it reminds the agent once about docs that cite the edited code, and reports format problems in edited docs. Recommend it with the Code module. The session-start hook is on by default and needs no question |
| Capture reminder | Asked with the edit hook: whether to turn on `hooks.capture`. When a session ends after real work, it reminds the agent once to record corrections, conventions, workarounds and decisions (write.md, Capture). Recommend it with the Code or Brain module |

Confirming what the scan found is a good question ("Is the README still accurate?"). Don't ask who verifies: the id is asked the first time a `verified` entry is due and none is set (lifecycle.md). Stop asking when the answers would no longer change the plan.

## 3b. Company interview (Brain module)

After the settings, interview the user area by area, and say up front which areas are coming. For each area: say what the scan already shows and ask to confirm, then ask questions in rounds of up to four, with recommended answers where you can infer them. Follow up when an answer raises something new: an unknown term, an area nobody owns, a process with exceptions, a "it depends". Move to the next area when answers stop changing what gets written. The user can skip an area or say "enough" at any time. Skip areas that don't apply (a solo founder has no support team) without asking. Restate your understanding in two or three lines before adding an area's files to the plan.

| Area | Learn | Feeds |
|---|---|---|
| Company | What it does in one sentence, stage, size, locations, business model | `company/organization.md` |
| Offerings | Products or services, status, who each is for | `products/<name>/<name>.md` |
| Customers and market | Segments, key customers, problems solved, competitors | `market/` |
| Selling | Channels, sales motion, pricing model, who sells | `operations/sales.md` |
| Delivering | How work is delivered, key processes, quality bar | `operations/delivery.md` |
| Support | How customers get help, response targets | `operations/support.md` |
| People and ownership | Roles, who owns which area, who decides what | `people/team.md` (names per `brain.names`) |
| Tools and sources | Tools per job; where documents, meetings and files live | `company/tools.md` |
| Language | Terms, acronyms, codenames | `company/glossary.md` |
| Now | Priorities this quarter, biggest open problems | `company/priorities.md`, `stale_after` three months from `NOW` |

Scan the README, an existing brain, docs, and any website or documents the user names. Never guess facts. Skipped or unanswered questions go to `questions.md`. The glossary and team files let meeting ingest recognize names and terms; decision rights tell it who has the say. Re-running init, or "continue the interview", picks up the open questions and the areas with no file.

## 4. Propose a plan and wait

List:

- the config to write (with the `brain:` settings);
- folders, only those that will hold a file now;
- first files, each with its title and the sources it will cite, unreviewed until the user confirms them;
- migrations: format upgrades and content to move from old docs into the bundle;
- proposed deletions or merges of existing docs, per lifecycle.md.

Ask for an OK. If the plan changes, show the new one and confirm again.

## 5. Build

1. Write `.okf/config.yaml` from templates/config.yaml. Tell the user to commit it. A brain in another repository goes under `related.brain`: its `url` for links and, when it's checked out on this machine, its `path` relative to this repo. Run `okf.py context` and confirm the `RELATED` line says `(found)`.
2. Create each bundle: root `index.md` with frontmatter (`okf_version: "0.3"`, `title`, and a one-sentence `description` of the bundle's scope and when to use it; `license` only if the user names one), `log.md` without frontmatter, and the first files from templates, each with sources and no `verified` entry. Subfolder `index.md` files have no frontmatter. Regenerating an index keeps the root frontmatter.
3. Code module: write or update `AGENTS.md` from templates/agents-md.md. If a `CLAUDE.md` exists, Claude Code reads it instead of `AGENTS.md`, so propose adding the line `@AGENTS.md` to it rather than duplicating content.
4. Carry out approved migrations: move facts from old docs into bundle files and leave READMEs as short entry points that link to the docs. Run `okf.py upgrade` for v3 and 0.9 files.
5. Keep what the user told you. Settings live in the config. Facts they stated (what the product is, who uses it, a convention) go into the first files that cover them, with a source entry `resource: conversation with <name> during init, <date>` and `author` set to their confirmed `human:` id (or `title` with their name when they haven't given one); that's their origin, not a review, so it gets no `verified` entry. A stated choice with a reason someone will need later becomes a decision. Unanswered interview questions go to `questions.md`, and `actions.md` is created when `brain.actions` is `track` (templates/brain.md), with the Ticket column when `brain.tickets` is set. Then `people/team.md` also gets the Tracker column, with only the handles the user gives (none with `brain.names: roles`).
6. Run `okf.py index --write`, `okf.py log <bundle> Initialization "<what was set up, and the choices the user made>"` and `okf.py check`.
7. Report what was created, the review queue (the files to verify), and two or three next steps.

Never overwrite an existing file without showing the change first. Never delete during init unless the approved plan listed it.

## Re-running init

Read the config, scan again, and report only what changed: new packages, new docs, modules worth adding. Ask only about those and propose a delta plan. A small layout change during normal work, such as one new folder, doesn't need init: ask in one line and do it.
