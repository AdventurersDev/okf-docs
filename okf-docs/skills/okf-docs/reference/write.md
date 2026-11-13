# write

Put knowledge in the right file: capture what was learned or built, record decisions, ingest meetings and files, co-write long documents.

## When to write

Every file costs reading time and upkeep, and each one can go stale. Keep docs few and true.

- **Update** a doc whenever a fact it states has changed. A wrong doc is worse than none.
- **Add a file** only when all three hold: someone will need it later (a teammate, an agent, a user); they can't get it quickly from the code or the commit message; and it will still be true in a few months. Typical: a user-visible feature, a limit, an API or config option, a runbook after an incident, a material decision.
- **Don't write** about bug fixes (the commit says it), refactors, renames, tests, dependency bumps, internal helpers, experiments, or code that is still changing. How one function works belongs in a code comment.
- **Prefer a line** in an existing file over a new file.
- **Once per task:** document at the end of a piece of work, not after each edit. Batch the changes.
- **Unasked:** when the user didn't ask for docs, update the docs whose facts changed and say so in one line. Propose new files and decisions instead of writing them, all in one line: "Worth recording the move to Postgres as a decision?" When the user asks, write.

## 1. Decide where it goes

- **Implementation truth** goes in the repo's docs bundle (kinds/docs.md): behavior, limits, architecture, APIs, schemas, conventions, runbooks, security as built, technical decisions.
- **Business truth** goes in the brain (kinds/brain.md): purpose, audience, problem, strategy, pricing model, customers, initiatives, how the team works, business decisions. Raw inputs (meeting notes, transcripts, emails, research) become brain assets.
- **Public wording** of either doesn't go here; publish builds pages from these files.
- **Both:** two files that link to each other and share no prose. Tell the user in one line what went where.
- If the right module is off, or the bundle lives elsewhere and isn't reachable, finish what you can and list what belongs there.

## 2. Update before you create

Search first, with `okf.py find <words>` and the folder's `index.md`. If a file already covers the subject (same `scope` and type), update it. Create a file only for a separate subject; two files on one subject is a defect that check reports.

## 3. Write the file

1. **New file:** start from the type's template in templates/<kind>.md, replace every `<…>` (check flags leftovers), and fill the frontmatter: `type`, `title`, a one-sentence `description`, `scope` if narrower than the bundle root, `specificity`, and `generated` with `by: <agent ACTOR>` and `at: <NOW>`.
2. **Body** per writing.md: exact values instead of adjectives; footnotes from claims to their sources.
3. **`sources`:** what you read (code paths, decision files, assets, URLs). Never a guess.
4. **Changing facts** in an existing file: edit in place, bump `generated.at`, remove `verified` entries. A typo or wording fix changes neither.
5. **Links:** to related files, in both directions where a reader would follow them; to the other layer (brain or repo docs) through the `related` URL in config.
6. **Finish:** `okf.py index --write` if you added, moved or deleted a file; `okf.py log <bundle> <Kind> "<what>"` for structural changes; `okf.py check <paths>`, and fix what it reports.

## Decide

A decision is material when someone will need the rationale later or it changes a constraint others build on. When the user asks to record one, it's material. When you notice one yourself and aren't sure, ask in one line; don't write it unasked.

- Write `decisions/NNN-title.md` with the next free number, from the decision template.
- Record only the rationale and alternatives that were stated. Otherwise write "Not recorded." Never invent them.
- Overturning an earlier decision: the new file gets `supersedes`; the old one gets `status: deprecated` and `superseded_by`; each links the other.
- Update the files the decision changes and list them under "Affected".

## Ingest (Brain module)

For meeting notes, transcripts, emails and documents:

1. Write the asset metadata file `assets/YYYY-MM-DD-slug.md` from the template. Store a raw file under `assets/files/` only if the user supplied one and wants it kept.
2. Summarize it in three to six lines.
3. Extract the claims and tag each one: **update** (a fact for an existing canonical file), **decision**, **observation** (a single unverified finding), **docs** (an implementation detail for repo docs) or **ignore**.
4. Apply them: updates and decisions as above; observations as `observations/YYYY-MM-DD-slug.md` with `stale_after`. Cite the asset in `sources` wherever a claim landed.
5. Sensitive content: never copy third parties' personal data, credentials, financial account details, or personnel and health matters into knowledge files. Note in the asset metadata that the raw file contains them. If unsure, ask.
6. Report one line per class, with counts and paths.

## Co-write

For long documents such as design docs, proposals and guides:

1. **Context:** ask for the goal, the reader and the constraints, and read the sources the user names. At most three questions per round.
2. **Outline:** headings with one line each. Confirm before drafting.
3. **Draft section by section** and ask for corrections after each one, not at the end.
4. **Reader test:** give the `okf-docs:okf-reader` agent only the draft and five to ten questions a reader would ask; without the agent, answer them yourself from the draft alone. Fix what it got wrong, found ambiguous or couldn't answer.
5. **Debloat** per writing.md and report the word count.

## Capture

For a bare `write`, or "document what we did": walk through the conversation. Each piece of implementation or business knowledge that was produced or changed and passes "When to write" goes through the steps above; each material choice goes through Decide. Report what landed where, and in one line what you left out and why.

## After engineering work

At the end of a task that changed behavior in code, when the Code module is on:

- Find the docs that cite the changed files (`okf.py find`, `okf.py stale`) and update the facts that changed.
- A new user-visible feature or a material choice: propose the new file or decision in one line, per "When to write". Don't write it unasked.
- Update `AGENTS.md` if commands, layout or conventions changed.
- Tell the user in one line, for example: "Docs: updated product/export.md (new size limit)."
- Skip all of this when nothing user- or developer-visible changed, and while the code is still being reworked.
