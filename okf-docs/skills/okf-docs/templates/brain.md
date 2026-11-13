# Templates: brain

For the classes in [kinds/brain](../reference/kinds/brain.md). Start from the frontmatter plus the body for the class. Replace every `<…>`; check and lint flag what's left. Delete a section that has nothing true to say instead of filling it.

## Frontmatter

```yaml
---
type: <type from kinds/brain.md>
class: <canonical, decision, observation, asset or reference>
title: <title in a few words>
description: <the most useful fact about it, in one sentence>
scope: <acme/area>
specificity: <general, specific or exact>
credibility: <reported or inferred>
generated:
  by: <agent ACTOR>
  at: <NOW>
sources:
  - id: <short id>
    resource: <../assets/2026-11-12-customer-call-globex.md>
---
```

Leave out `scope` when it is the bundle's root scope. Each key is explained in [format](../reference/format.md).

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

[^<short id>]: <assets/2026-11-12-customer-call-globex.md>
```

## decision

Use the decision body from [templates/docs](docs.md#decision), with `class: decision`. Record only the rationale and alternatives that were stated; otherwise write "Not recorded."

## observation

Add `stale_after: <NOW plus three months>` to the frontmatter. `type` is customer, metric, market or hypothesis.

```markdown
# <the finding, as a statement>

<The statement in one sentence, with who observed it and when.>

## Evidence

- <what was seen, where and when>[^<short id>]

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

## Summary

<Three to six lines.>

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
