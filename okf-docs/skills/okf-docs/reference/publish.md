# publish (Publish module)

Turn public facts into pages people want to read: a help center, developer docs, a changelog, team updates. Pages are views: every fact on a page comes from a bundle file the page cites.

## Rules

- Public pages use only files with `visibility: public`. Making a file public is the user's call: ask, and list the files. Team updates are internal (`type: update`, no `visibility: public`) and may cite internal files.
- No new facts on pages. A missing fact goes into its source file first (write), then onto the page.
- Every page lists its sources and has no human `verified` entry until a human signs it off. Public pages also carry `visibility: public`.
- The first page for a site without `voice.md` waits for the user's answers to step 1. Write nothing to the site before they reply.
- Never deploy, push or post without the user's go-ahead.

## Steps

1. **Target, reader and voice:** which site (kinds/site.md) and which page or release. Then read the site's `voice.md`. If it's missing, stop and ask once for that site before you outline or write anything, even when the existing pages make the answers look obvious. At most three questions, each with a recommended answer inferred from the existing pages, the README and the brain, so the user can reply "defaults":
   - **Reader:** who they are, what they already know, and what they're trying to do.
   - **Tone:** for example plain and friendly, neutral and precise, or formal; and how to address the reader ("you", or du or De in Norwegian).
   - **Language:** language and locale (spelling, dates, numbers), and product terms to use or avoid.

   Write the answers to `voice.md` from the template, and reuse them for every later page in that site. When the brain has a brand voice file, `voice.md` links to it and holds only what differs for this site. A page for a different reader than the site's, such as admins in a user help center, names that reader in its outline.
2. **Gather** the public source files. For a changelog, also the `log.md` entries and git tags since the last release; for a team update, the log entries since the last update.
3. **Outline:** each page's title and the task or question it answers. For developer docs, sort pages into tutorial, how-to, reference and explanation (Diátaxis). Confirm the outline when the job is more than one page; for one page the user asked for, go on to the draft and put the outline in front of them at sign-off.
4. **Draft** from the sources in the site's voice and the public shape (writing.md): steps, tables, diagrams, screenshot placeholders. Tone sets register, never padding: a friendly page is plain and warm, not enthusiastic, and the debloat rules still apply.
5. **Debloat** with the procedure in writing.md and report the word counts.
6. **Reader test:** give the `okf-docs:okf-reader` agent only the page and five to ten questions a reader would ask; without the agent, answer them yourself from the page alone. Fix what fails.
7. **Sign-off:** show the page and its sources. On approval, add the human `verified` entry.
8. **Render or deploy** only when the user asks: with the site tool from config, or with the docx, pdf or slide skills, if installed, for those formats.

## Formats

| Target | Shape |
|---|---|
| Help center | Task-first pages. Troubleshooting as symptom → cause → fix |
| Developer docs | Diátaxis: tutorials, how-to guides, reference, explanation |
| Changelog | One entry per release under Added, Changed, Fixed, Removed and Security. User-visible changes only, each linked to its docs page |
| Team update | Progress, plans, problems: three to five bullets each, linked to the files that changed |
| FAQ | The question as the heading, the answer in the first sentence |

## Staleness

`okf.py check` and `okf.py stale` mark a page stale when one of its sources changed after the page was verified, or is stale itself. To refresh a page, re-read the changed sources, update the page, and get sign-off again.

For the site's look (theme, layout, components), use the impeccable skill if it is installed. This skill owns the words and the structure, not the design system.
