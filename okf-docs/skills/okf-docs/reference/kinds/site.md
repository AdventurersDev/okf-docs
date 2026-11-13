# Kind: site (Publish module)

Pages built from bundle facts: a public help center, developer docs and changelog, and internal team updates. A site bundle is an OKF bundle whose pages cite their sources. A site generator (MkDocs, Docusaurus, Starlight, VitePress) or a help-center tool renders it.

## Layout

Set by the preset (presets/site.md); the path comes from config, such as `help/`, `developers/` or `changelog/`. Never put a site inside the internal docs bundle.

## Page frontmatter

```yaml
---
type: how-to
title: Export your data
description: Download a workspace as CSV or JSON from Settings.
visibility: public
credibility: reported
generated:
  by: okf-docs/0.9.1
  at: 2026-11-12T14:03:22+01:00
sources:
  - id: export
    resource: ../../docs/product/export.md
---
```

Site generators ignore keys they don't know. If one rejects them, render a copy without the OKF keys into the generator's content folder at publish time; don't change the bundle.

## Types

| `type` | The page answers | Template |
|---|---|---|
| `tutorial` | "Teach me": a guided first success | tutorial |
| `how-to` | "How do I…": one task, in steps | how-to |
| `reference` | "What exactly is…": options, fields, limits | reference |
| `explanation` | "Why does it work this way" | explanation |
| `troubleshooting` | "It's broken": symptom → cause → fix | troubleshooting |
| `faq` | Short questions, each answered in its first sentence | faq |
| `release` | One changelog entry | release |
| `update` | One team update. Internal: no `visibility: public` | update |
| `voice` | Not a page: the site's reader, tone and language, in `voice.md` at the site root. Internal: no `visibility: public` | voice |
