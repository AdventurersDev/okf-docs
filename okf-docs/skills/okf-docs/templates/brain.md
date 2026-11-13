# Templates: brain

For the classes in [kinds/brain](../reference/kinds/brain.md). Start from the frontmatter plus the body for the class. Replace every `<…>`; check and lint flag what's left. Delete a section that has nothing true to say instead of filling it.

## Frontmatter

```yaml
---
type: <type from kinds/brain.md>
x-okfdocs-class: <canonical, decision, observation, asset, reference or tracker>
title: <title in a few words>
description: <the most useful fact about it, in one sentence>
x-okfdocs-scope: <acme/area>
x-okfdocs-specificity: <general, specific or exact>
generated:
  by: <agent ACTOR>
  at: <NOW>
sources:
  - id: <short id>
    resource: <../assets/2026-11-12-customer-call-globex.md>
---
```

Leave out `x-okfdocs-scope` when it is the bundle's root scope. Each key is explained in [format](../reference/format.md).

## canonical

```markdown
# <entity name>

<What it is, in one or two lines.>

## Why it exists

<Who it serves and the problem it solves.>

## Current position

<The facts as of now: numbers, owners, status, dates.>[^<short id>]

## Related

- [<related file title>](<relative/path.md>)

## History

- <YYYY-MM-DD> [<asset or decision title>](<relative/path.md>): <a few words>

[^<short id>]: <assets/2026-11-12-customer-call-globex.md>
```

Keep `## History` for entity files (customer, client, product, initiative); delete it elsewhere. Newest first, one line each, added with `okf.py history` (format.md). Adding a line leaves `generated.at` alone.

## process

For `operations/<name>.md` (sales, delivery, support). `type: process`, canonical.

```markdown
# <how we sell, deliver or support>

<What this process is for, in one line.>

## Steps

1. <step, who does it>[^<short id>]

## Owner and decision rights

<Who owns it and who decides what: discounts, exceptions, escalations.>

## Tools and terms

- <tool or term, linked to company/tools.md or company/glossary.md>
```

## glossary

`company/glossary.md`, `type: concept`, canonical. Meeting ingest reads it to recognize terms.

```markdown
# Glossary

| Term | Means | Also called |
|---|---|---|
| <term or acronym> | <one-line definition> | <alias or codename, or "-"> |
```

## priorities

`company/priorities.md`, `type: concept`, canonical, with `stale_after` three months from `NOW`.

```markdown
# Priorities

## This quarter

1. <priority, with its owner>

## Biggest open problems

- <problem>
```

## team

`people/team.md`, `type: function`, canonical. Names follow `brain.names`; no contact details. Meeting ingest reads it to know who owns what and who has the say.

```markdown
# Team

| Person or role | Owns | Decides |
|---|---|---|
| <name or role, per brain.names> | <areas and responsibilities> | <decision rights, for example "discounts up to 20%"> |
```

With `brain.tickets` set, add a `Tracker` column at the end: the person's handle in the ticket system, used to assign tickets, or `-`. Only handles the user gives; none with `brain.names: roles`.

## actions

`actions.md` at the brain root, only with `brain.actions: track`. `type: action-list`, `x-okfdocs-class: tracker`; frontmatter has `title`, `description` and `generated` only. Keep these exact headings and columns; check parses them.

```markdown
# Actions

## Open

| Owner | Action | Due | From | Added |
|---|---|---|---|---|
| <owner> | <the action in one line> | <YYYY-MM-DD, or -> | [<asset title>](assets/<YYYY-MM-DD-slug>.md) | <YYYY-MM-DD> |

## Done

| Owner | Action | Due | From | Added | Done |
|---|---|---|---|---|---|
```

With `brain.tickets` set, both tables get a `Ticket` column after `Action`: the ticket's link, `-` when the action needs none, or empty until it is synced (write.md, Tickets).

```markdown
| Owner | Action | Ticket | Due | From | Added |
|---|---|---|---|---|---|
| <owner> | <the action in one line> | [<ENG-412>](<ticket URL>) | <YYYY-MM-DD, or -> | [<asset title>](assets/<YYYY-MM-DD-slug>.md) | <YYYY-MM-DD> |
```

## questions

`questions.md` at the brain root. `type: question-list`, `x-okfdocs-class: tracker`. Same rules as actions.

```markdown
# Questions

## Open

| Area | Question | Why it matters | Asked |
|---|---|---|---|
| <Selling> | <the question> | <which file or decision it blocks> | <YYYY-MM-DD> |

## Answered

| Area | Question | Answer in | Answered |
|---|---|---|---|
```

## decision

Use the decision body from [templates/docs](docs.md#decision), with `x-okfdocs-class: decision`. Record only the rationale and alternatives that were stated; otherwise write "Not recorded."

## observation

Add `stale_after: <NOW plus three months>` to the frontmatter. `type` is customer, metric, market or hypothesis.

```markdown
# <the finding, as a statement>

<The statement in one sentence, with who observed it and when.>

## Evidence

- <what was seen, where and when>[^<short id>]
- From a customer call: "<one short verbatim quote, under 20 words>", <role, organization>[^<short id>]

## Supports or contradicts

- <the file it supports or contradicts, linked, and how>

## Promotion condition

<What would make it canonical: a second independent source, a decision, or a confirmation, and from whom.>
```

## asset

A metadata file in `assets/YYYY-MM-DD-slug.md`. `type` is meeting, transcript, email, note, research or document. In `sources`, give the raw file (`files/YYYY-MM-DD-slug.ext`), a link, or `pasted in conversation, <date>`.

```markdown
# <asset title>

| Property | Value |
|---|---|
| Kind | <meeting, transcript, email, note, research or document> |
| Date | <date, YYYY-MM-DD> |
| Origin | <who it came from, as roles and organizations> |
| File | [<file name>](<files/2026-11-12-customer-call-globex.txt>), or "not stored" |
| Sensitive content | <none, or what kind; kept out of the summary> |

**What it was:** <type, purpose, and participants by role or name, per brain.names>.

## Summary

<Three to six lines.>

## Decisions

- <what was decided, by whom>[, <timestamp>] - or "No clear decisions."

## Actions

- <owner>: <the deliverable>[, due <YYYY-MM-DD>][, <timestamp>][ ([<ENG-412>](<ticket URL>))] - or "No clear actions."

## Extracted claims

| Claim | Tag | Landed in |
|---|---|---|
| <the claim in one line> | <update, decision, observation, docs or ignore> | [<file title>](<relative/path.md>) |
```

## reference

External context the company doesn't own: a report, a competitor, an article.

```markdown
# <source name>

<What it is and why it matters to us, in one or two lines.>

## Key points

- <a point, with the page or section it comes from>[^<short id>]

## What we take from it

<How it affects our products, market or decisions, linked to those files.>
```
