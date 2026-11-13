# Templates: site

For the page types in [kinds/site](../reference/kinds/site.md). Start from the frontmatter plus the body for the type. Replace every `<…>`; check and lint flag what's left. Apply the visual rules in [writing](../reference/writing.md) to every page.

## Frontmatter

```yaml
---
type: <type from kinds/site.md>
title: <task or concept, as the reader would search for it>
description: <what the reader gets from the page, in one sentence>
x-okfdocs-visibility: public
generated:
  by: <agent ACTOR>
  at: <NOW>
sources:
  - id: <short id>
    resource: <../docs/product/data-export.md>
---
```

Team updates (`type: update`) leave out `x-okfdocs-visibility: public`. Every source of a public page must itself be `x-okfdocs-visibility: public`.

## tutorial

```markdown
# <the outcome: "Send your first invoice">

<What the reader has at the end, and how long it takes.>

## Before you start

- <account, plan, role or tool needed>

## 1. <first step title>

<One action, then what the reader sees.>

<!-- screenshot: <what it shows> -->

## 2. <next step title>

<One action, then what the reader sees.>

## Next steps

- [<next page title>](<relative/path.md>)
```

## how-to

```markdown
# <the task as an imperative: "Export your data">

<One line: what the reader gets, and any requirement such as a plan or role.>

1. Go to **<menu label>** > **<page label>**.
2. Select **<button label>**.

<What the reader sees when it worked.>

## If it doesn't work

- <symptom in a few words>: <fix>. See [<troubleshooting page title>](<relative/path.md>).
```

## reference

```markdown
# <what is listed: "Export settings">

<One line: what this page lists and where it applies.>

| Option | Values | Default | Notes |
|---|---|---|---|
| <option name> | <allowed values> | <default value> | <limits, plan, effect> |
```

## explanation

```markdown
# <the concept: "How rate limits work">

<The idea in two lines.>

## <one aspect of it>

<The explanation with one concrete example. Add a diagram if more than three steps or actors are involved.>

## Related

- [<related page title>](<relative/path.md>)
```

## troubleshooting

```markdown
# <the symptom as the reader says it: "Export never finishes">

<What the reader sees, with the exact error text.>

## <first cause in a few words>

<How to tell this is the cause.>

1. <Fix, one action per step.>

## <second cause in a few words>

<How to tell this is the cause.>

1. <Fix, one action per step.>
```

## faq

```markdown
# <product area> FAQ

## <a question, as the reader asks it?>

<The answer in the first sentence. Details after, with a link to the full page.>
```

## release

`title` is the version, such as `v2.4.0`. Leave out a section with no entries.

```markdown
# <version number> (<release date, YYYY-MM-DD>)

## Added

- <a user-visible change in one line>. [<docs page title>](<relative/path.md>)

## Changed

- <a user-visible change in one line>.

## Fixed

- <what was broken, now fixed>.

## Removed

- <what is gone, and what to use instead>.

## Security

- <the fix, and whether users need to act>.
```

## update

Internal: no `x-okfdocs-visibility: public`. Three to five bullets per section.

```markdown
# <team or project> update (<date, YYYY-MM-DD>)

## Progress

- <what shipped or moved>, in [<changed file title>](<relative/path.md>).

## Plans

- <what's next, with the owner's role and a target date>.

## Problems

- <what's blocked or at risk, and what would unblock it>.
```

## voice

`voice.md` at the site root. No `x-okfdocs-visibility: public`: it guides writers and is never published.

```markdown
---
type: voice
title: Voice for <site>
description: <reader> reading <site>; <tone>; <language>.
generated:
  by: <agent ACTOR>
  at: <NOW>
---

# Voice for <site>

## Reader

<Who they are, what they already know, what they're trying to do.>

## Tone

<Register, for example plain and friendly.> Address the reader as <"you" / du / De>.

## Language

<Language and locale, for example en-US or nb-NO: spelling, dates, numbers.>

| Use | Avoid |
|---|---|
| <product term> | <word to avoid> |

## Brand voice

<Link to the brain's brand voice file, or "None.">
```
