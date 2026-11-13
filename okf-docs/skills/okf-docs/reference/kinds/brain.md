# Kind: brain (Brain module)

The company's business knowledge: who we are, what each product is for, who we serve, what we decided and why, and how the team works. Raw inputs (meetings, transcripts, emails, research) are kept as assets.

## What belongs here

The organization, its functions, principles, strategy and go-to-market; each product's purpose, audience, problem, positioning and pricing model; customers, clients, partners and initiatives; the team handbook; business decisions; observations; assets. How anything is built belongs in the repo's docs, linked from here.

## Layout

Top-level folders are categories. Create the core ones below as they get content, and add others (finance, sales, technology, initiatives) when the company needs them. Depth is category → entity → files, never deeper: paths that encode today's org chart break at the next reorg. `decisions/`, `observations/` and `assets/` stay flat, apart from `assets/files/`.

```
brain/
├── index.md
├── log.md
├── company/          who we are: organization, functions, principles, strategy
├── products/<name>/  what each product is for; links to its repo docs
├── market/           who we serve: audiences, problems, competitors, clients/<name>/
├── people/           the team handbook (handbook preset)
├── decisions/        NNN-short-title.md
├── observations/     YYYY-MM-DD-slug.md
└── assets/           YYYY-MM-DD-slug.md metadata; raw files in assets/files/
```

## Classes and types

Every file has a `class`, which sets its lifecycle (lifecycle.md):

| `class` | Is | `type` examples |
|---|---|---|
| `canonical` | Current truth: small, stable, verified | organization, function, principle, strategy, product, audience, problem, use-case, messaging, customer, client, initiative, policy, process |
| `decision` | A material choice and its rationale | decision |
| `observation` | A finding not yet accepted as truth | customer, metric, market, hypothesis |
| `asset` | A raw input, described by a metadata file | meeting, transcript, email, note, research, document |
| `reference` | External context we don't own | report, competitor, article |

Storing an asset doesn't make it true. Claims leave an asset only through ingest (write.md) and promotion (lifecycle.md).

## Rules

- Observations carry `stale_after`, three months from `NOW` unless the user says otherwise.
- Assets record where they came from in `sources`: the file, a link, or `pasted in conversation, <date>`.
- Sensitive content: never copy third parties' personal data, credentials, financial account details, or personnel and health matters into canonical, observation or decision files. Mark assets that contain them and keep that content out of summaries.
- One customer's statement is an observation, however detailed.

## Links to repo docs

A product's brain file says why the product exists and who it serves, then links to the repo's docs using the `related` URL in config. The repo docs link back. Neither repeats the other.
