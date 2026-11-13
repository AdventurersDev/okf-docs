# OKF Docs

Writes, checks and publishes documentation as [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (OKF v0.3) bundles: repo docs and `AGENTS.md` for coding agents, a company brain for team and business knowledge, and public help, developer and changelog pages with the AI bloat removed.

```
/plugin marketplace add AdventurersDev/okf-docs
/plugin install okf-docs@waybound
```

Start with `/okf-docs init` in your project. It scans what exists, asks a few questions, and writes nothing until you approve its plan. With the Brain module it also interviews you about the company. Before writing what people tell it, it restates it and asks about what is unclear. Then use `/okf-docs` for status, or `write`, `meeting <file>`, `ask`, `check`, `sync` and `publish`. If another skill is also called `okf-docs`, use the full name, `/okf-docs:okf-docs`.

It also records corrections and conventions you state while working, and `check brain` reviews new inputs and proposes what to promote. With `brain.tickets` set, actions from meetings become tickets in your ticket system, through the connector you already use: it links an existing ticket instead of creating a duplicate, and creates nothing without your OK.

The checks need Python 3.8 or later on `PATH`, standard library only.

The full guide is in the [repository README](https://github.com/AdventurersDev/okf-docs#readme). Apache-2.0.
