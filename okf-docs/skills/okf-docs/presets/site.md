# Presets: site

Starting layouts for pages built from bundle facts ([kinds/site](../reference/kinds/site.md)). Each target is its own bundle with `kind: site` in config, in its own folder, never inside the internal docs bundle.

If the repo already has a site tool (`mkdocs.yml`, `docusaurus.config.*`, `astro.config.*` with Starlight, `.vitepress/`), set `publish.tool` in config and keep the bundle in its own folder. At publish time, copy the pages into the tool's content folder and leave out `index.md`, `log.md` and `voice.md`: they are OKF files for writers, not pages, and some tools reject a page without a `title`.

## help-center

For users finishing a task in the product.

```
help/
├── index.md
├── log.md
├── voice.md           reader, tone, language (publish.md asks once)
├── getting-started/   first tasks: sign up, set up, invite the team
├── guides/            one task per page (how-to)
├── troubleshooting/   symptom, cause, fix
└── faq.md
```

First pages: the three to five tasks new users do first, drafted from the public concepts in the product docs.

## developer

For developers integrating with the product, in the four Diátaxis kinds.

```
developers/
├── index.md
├── log.md
├── voice.md
├── tutorials/     a guided first success: "Make your first API call"
├── how-to/        one task each: "Paginate results"
├── reference/     endpoints, fields, errors, limits
└── explanation/   how and why: "How rate limits work"
```

First pages: a quickstart tutorial, an authentication how-to, and reference pages from the public files in `system/api/`. When an OpenAPI or GraphQL schema exists, link the generated reference instead of rewriting it, and write only what the schema can't say.

## changelog

```
changelog/
├── index.md
├── log.md
├── voice.md
└── YYYY-MM-DD-vX.Y.Z.md   one release file per version
```

Entries come from the log and git tags since the last release, limited to user-visible changes.

## updates

Internal team updates, `updates/YYYY-MM-DD-slug.md` with `type: update`. They may cite internal files and never get `x-okfdocs-visibility: public`.
