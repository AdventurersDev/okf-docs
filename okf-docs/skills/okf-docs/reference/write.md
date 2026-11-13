# write

Put knowledge in the right file: capture what was learned or built, record decisions, ingest meetings and files, co-write long documents.

## When to write

Every file costs reading time and upkeep, and can go stale. Keep docs few and true.

- **Update** a doc whenever a fact it states has changed. A wrong doc is worse than none.
- **Add a file** only when all three hold: someone will need it later (a teammate, an agent, a user); they can't get it quickly from the code or the commit message; and it will still be true in a few months.
- **Don't write** about bug fixes (the commit says it), refactors, renames, tests, dependency bumps, internal helpers, experiments, or code that is still changing. How one function works belongs in a code comment.
- **Prefer a line** in an existing file over a new file.
- **Unasked:** update the docs whose facts changed and say so in one line. Propose new files and decisions in one line instead of writing them: "Worth recording the move to Postgres as a decision?"

## Understand first

Before writing knowledge that comes from people (conversation, meetings, documents, init answers), make sure you understand it.

1. Read the related files: `okf.py find`, the folder index, and in a brain the glossary and team files.
2. Restate in one to three lines what you think it means and where it would go.
3. Find what is unclear: unknown terms or acronyms, who owns it, decided or only proposed, scope (company, one product, one customer), still current, conflicts with existing files.
4. Ask about those, at most four questions per round (AskUserQuestion when available, recommended option first). Ask only what changes what gets written, never what the bundles answer.
5. Write only what is stated clearly or confirmed. In a brain, put unanswered questions in `questions.md`; elsewhere leave the item out and say so in one line.
6. Stop when answers no longer change the content.

Skip the questions when the source is code and the fact is unambiguous, or the user said to file without asking: write what is clear, list the rest in the report.

## 1. Decide where it goes

- **Implementation truth** goes in the repo's docs bundle (kinds/docs.md): behavior, limits, architecture, APIs, schemas, conventions, runbooks, security as built, technical decisions.
- **Business truth** goes in the brain (kinds/brain.md): purpose, audience, problem, strategy, pricing model, customers, initiatives, how the team works, business decisions. Raw inputs (meeting notes, transcripts, emails, research) become brain assets.
- **Both:** two files that link to each other and share no prose; say in one line what went where.
- Module off or bundle unreachable: finish what you can and list what belongs there.

## 2. Update before you create

Search first: `okf.py find <words>` and the folder's `index.md`. If a file covers the subject (same `x-okfdocs-scope` and type), update it. Two files on one subject is a defect check reports.

## 3. Write the file

1. **New file:** start from the type's template in templates/<kind>.md, replace every `<…>` (check flags leftovers), and fill the frontmatter: `type`, `title`, a one-sentence `description`, `x-okfdocs-scope` if narrower than the bundle root, `x-okfdocs-specificity`, and `generated` with `by: <agent ACTOR>` and `at: <NOW>`.
2. **Body** per writing.md: exact values, footnotes from claims to sources.
3. **`sources`:** what you read (code paths, decision files, assets, URLs). Never a guess. Add `author` (an actor such as `human:alex` or `team:finance`) when you know who stated it.
4. **Changing facts** in an existing file: edit in place and bump `generated.at`; leave the `verified` entries, which stop counting. A typo, wording fix or history line changes neither. Never edit the computation code of an Attested Computation; only the user does.
5. **Links:** to related files, in both directions where a reader would follow them; to the other layer (brain or repo docs) through the `related` URL in config.
6. **Finish:** `okf.py index --write` if you added, moved or deleted a file; `okf.py log <bundle> <Kind> "<what>"` for structural changes; `okf.py check <paths>`, and fix what it reports.

## Decide

A decision is material when someone will need the rationale later or it changes a constraint others build on. A decision the user asks to record is material. When you notice one and aren't sure, ask in one line; don't write it unasked.

- Write `decisions/NNN-title.md` with the next free number, from the decision template.
- Record only the rationale and alternatives that were stated. Otherwise write "Not recorded." Never invent them.
- Overturning an earlier decision: the new file gets `x-okfdocs-supersedes`; the old one gets `status: deprecated` and `superseded_by`; each links the other.
- Update the files the decision changes and list them under "Affected".

## Ingest (Brain module)

For meeting notes, transcripts, emails and documents. Read the whole source first, and check the glossary and team files for names and terms.

**Meetings and transcripts: understand first, then extract.** Apply "Understand first", plus:

1. **Name the meeting:** its type (customer call or interview, internal decision or planning meeting, standup, retrospective, other), why it was held, and who took part. Match people against `people/team.md` and the customer files; name them per `brain.names`.
2. **Connect it:** find what the brain holds on the topic: `okf.py find`, earlier assets, related decisions, the product file.
3. **Restate it** in two or three lines at the top of the preview (type, purpose, outcome), so the user can correct a wrong reading.
4. **Extract against that purpose.**
   - Customer call or interview: needs, pain points and requests (observations, each with one short verbatim quote of the customer's words as evidence, under 20 words); what we promised them (actions); anything they decided.
   - Internal decision or planning meeting: decisions, actions, changed priorities.
   - Standup: only blockers still open and commitments.
   - Retrospective: agreed changes to how the team works (an update to the process or how-we-work file).
5. **New or changed only.** A fact the brain holds is not recorded again; cite the meeting in that file's `sources` only if it adds evidence. A statement that contradicts a file is flagged in the preview as a conflict, never silently overwritten.
6. **Open questions:** an important question raised and left unanswered goes to `questions.md`, one line, with the meeting as the source.
7. **No speaker names:** name an owner or decider only when the text makes it clear; otherwise list the item as unclear and ask.

The bars for what to extract:

- **Decisions:** explicitly agreed or announced by someone with the say: "we'll go with X", "agreed", a clear yes to a concrete proposal. Not proposals, options weighed, preferences ("I think we should"), open debates, things to look into, or decisions someone else must still approve.
- **Actions** (unless `brain.actions: off`): a named person or team committed to, or was assigned and accepted, a concrete deliverable: "I'll send the contract by Friday"; "Sam, can you set up the pilot?" "Yes." Not ideas, "we should", "someone needs to", vague follow-ups, or work already done.
  An action names the deliverable, not a topic. Bad: "Follow up on pricing". Good: "Send Globex the revised pricing tiers by Friday 2026-11-20". Only a topic: list it as unclear and ask. No owner: mark it "needs an owner" in the preview and don't record it until someone is named.
- **Facts:** specific statements about the company, a product or a customer, tagged **update** (for an existing canonical file), **observation** (a single unverified finding; one customer's statement stays one) or **docs** (an implementation detail for repo docs).

Each item is one line: what, who (owner or decider), a due date only if one was said, and the timestamp when the transcript has them. Unclear items are not recorded; they go to the preview as questions. Most meetings yield 0-3 decisions and 0-5 actions: more means re-check each against the bar; none means say "No clear decisions or actions." Never write discussion summaries, key points, sentiment or long quotes; the one short quote per customer observation is the only exception.

**Several meetings at once:** ingest each as its own asset, then deduplicate actions and open questions (one row each, citing every meeting). Report themes in two or more meetings in at most three lines: a recurring need is a corroborated observation and a promotion candidate (lifecycle.md); conflicting decisions are flagged.

**Preview, then write.** Show the restated meeting, summary, decisions, actions, facts with their destination files, conflicts, and unclear items as questions; with `brain.tickets` set, also the ticket plan (Tickets, below). Write after the user's OK, or at once if told to file without asking (then list the unclear ones). Creating tickets always waits for the OK.

**Writing:**

1. The asset file `assets/YYYY-MM-DD-slug.md` (template) gets a "What it was" line (type, purpose, participants), a three-to-six-line summary, `## Decisions`, `## Actions` and the extracted claims: the meeting record. Keep a raw file under `assets/files/` only if the user supplied one and wants it.
2. A material decision also becomes `decisions/NNN-title.md` (Decide). A minor agreed decision stays in the asset.
3. Actions follow `brain.actions`: `report` (default) lists them in the asset and the chat report; `track` also appends them to the Open table of `actions.md` (lifecycle.md); `off` extracts none. With `brain.tickets` set, follow Tickets: when the user approves the tickets with the files, create them first so their links go in as you write; when you file without asking, write the files with the Ticket cells empty and fill in the links once the tickets exist.
4. Updates go into their canonical files; observations into `observations/YYYY-MM-DD-slug.md` with `stale_after`. Cite the asset in `sources` wherever a claim landed.
5. **History:** add one line to the `## History` section of each entity file the meeting is mainly about (customer, client, product, initiative), newest first, with `okf.py history <entity file> <asset file> --note "audit trail need; exports now fast"`. A few words, no summary. It changes only that section and leaves `generated.at`, so don't edit the line in by hand. No file for the entity yet: propose one only if it matters beyond this meeting (a customer, partner or initiative), else skip.
6. Names follow `brain.names` (kinds/brain.md). Never copy third parties' personal data, credentials, financial account details, or personnel and health matters into knowledge files; note in the asset that the raw file contains them. If unsure, ask.
7. Report one line per class, with counts and paths.

Emails and documents: same bar.

## Tickets (Brain module)

Only when the user has said they use a ticket system and want actions: `brain.tickets.system` set (by the user, never inferred from the connectors you see) and `brain.actions` not `off`. Then a meeting's clear actions become tickets in that system, and so do the open actions in `actions.md` when the user asks to sync them. The plugin holds no keys: use the connector for that system in this session (its MCP tools). Never call the system's API with a token, curl or a script. The one exception is GitHub Issues, below.

1. **Connector.** Find the tools for the system. None, or it needs sign-in: say so in one line ("Linear isn't connected; connect it with /mcp, then ask me to sync the actions"), record the actions per `brain.actions` with the Ticket cell empty, and carry on. No `target` set: ask which team, project or repository, and offer to save it in `brain.tickets.target`.
   **GitHub Issues without a connector:** the `gh` CLI may stand in, only when the context's `TICKETS` line says it is allowed: the system is `github`, actions are on, and the project is a git repository with a GitHub remote. Check `gh auth status` first; not signed in counts as no connector. Use only `gh issue list`, `gh issue view`, `gh issue create` and `gh issue comment`, each with `--repo <target>`; never `gh api`, other `gh` commands, or a token. Search with `gh issue list --state all --search "<terms>"`. GitHub issues have no due date: put it in the body.
2. **Look in the brain first.** For each action, look for the same deliverable in `actions.md` (Open and Done) and in the `## Actions` of earlier assets. If one has a ticket link, that is its ticket: link it, don't search or create. If one has no link, it is the same action: add no second row, and sync that one.
3. **Then search the ticket system** in the target: open tickets and tickets closed in the last 30 days, by the action's key terms (the customer, product or subject, and the deliverable) and by the owner. Read the titles and descriptions of what comes back. A match is the same deliverable for the same subject, whatever the wording: "Send Initech the pilot contract" matches "Initech pilot agreement". A ticket on the same subject with a different deliverable is not a match; mention it as related.
4. **Preview.** Add a Tickets section to the preview, one line per action: **create** (title, assignee or "unassigned", due date, target), **link** (the existing ticket's id, title, state and link; the default for every match and possible match), or **skip**. An action whose search failed or couldn't run is not created: say so and leave its Ticket cell empty for the next sync. Creating tickets needs the user's OK in this conversation even when they said to file the meeting without asking; that covers brain files only.
5. **Create** only the approved tickets. Title: the deliverable, as in the action line. Description: the owner, the due date if one was said, and the meeting's title and date with the asset's link (its web URL when `related.brain.url` gives one, else its path). Nothing else from the meeting: no transcript text, and no outside people's details beyond what `brain.names` allows. Assignee: the owner's handle from the Tracker column of `people/team.md`. No handle, an outside owner, or `brain.names: roles`: leave it unassigned and name the owner in the description, per `brain.names`. Set the due date when one was said; no labels, priority or estimates unless the user asks.
6. **Write the link back** into the action's line in the asset (`- Sam: send Initech the pilot contract, due 2026-11-20 ([ENG-412](https://linear.app/acme/issue/ENG-412))`) and, with `track`, into the Ticket column of its `actions.md` row. A linked action gets the existing ticket's link. A skipped one gets `-`, so check doesn't report it again.
7. **Report** in one line: "Tickets: 2 created (ENG-412, ENG-413), 1 linked (ENG-398), 1 skipped."

A linked ticket isn't changed. If the meeting changed its due date or owner, propose that change, or a comment on the ticket, in the preview, and make it only after the OK. Several meetings at once: deduplicate the actions first (Ingest), then one ticket per action. From then on the ticket system owns the action's state: lifecycle.md, Trackers.

## Co-write

For long documents such as design docs, proposals and guides:

1. **Context:** read the sources named, then ask about the goal, reader and constraints and anything the sources leave unclear: rounds of up to four questions, as many rounds as needed, until the answers stop changing the outline.
2. **Outline:** headings with one line each. Confirm before drafting.
3. **Draft section by section** and ask for corrections after each one, not at the end.
4. **Reader test:** give the `okf-docs:okf-reader` agent only the draft and five to ten reader questions (without the agent, answer them from the draft alone). Fix what it got wrong, found ambiguous or couldn't answer.
5. **Debloat** per writing.md and report the word count.

## Capture

Watch for knowledge that would otherwise be lost, while you work and at the end of a task. A bare `write`, or "document what we did", walks the whole conversation the same way. Each piece that passes "When to write" goes through the steps above.

| Trigger | Example | Goes to |
|---|---|---|
| The user corrects how something works or how we do it | "No, refunds go through the billing client, never direct" | The file that is wrong. A convention goes to `AGENTS.md` (repo), `how-we-work.md` or the process file (team), or the brain file (business) |
| The user states a convention or preference | "We always squash-merge", "Never email customers on Fridays" | `AGENTS.md`, `how-we-work.md`, or the matching process file |
| A workaround or gotcha that cost time | An environment quirk, a misleading error | The runbook or troubleshooting section in repo docs |
| A decision | "Let's go with Postgres" | Decide |
| The same steps done a third time | A manual release or setup | Propose a runbook or process file |

- A correction to an existing fact is applied right away and reported in one line.
- Everything else unasked is proposed in one line ("Unasked"). "Understand first" applies.
- Skip preferences that apply to this task only.
- Report what landed where, and in one line what you left out and why.

At the end of a task that changed behavior in code (Code module on):

- Find the docs that cite the changed files (`okf.py find`, `okf.py stale`) and update the facts that changed.
- A new user-visible feature or a material choice: propose the file or decision in one line. Update `AGENTS.md` if commands, layout or conventions changed.
- Say so in one line: "Docs: updated product/export.md (new size limit)."
- Skip all of this when nothing user- or developer-visible changed, and while the code is still being reworked.
