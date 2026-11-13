# Template: AGENTS.md

The file coding agents read first, at the repo root ([kinds/docs](../reference/kinds/docs.md)). No frontmatter. Keep it under about 100 lines: point to docs instead of copying them. Every command must be one you saw in the repo (package scripts, Makefile, CI config) or the user gave you. Replace every `<…>` and drop the rows that don't apply.

```markdown
# <repo name>

<One line: what this repo is and who uses it.> Product context: [<product name>](<brain URL from config>/products/<name>/<name>.md).

## Commands

| Task | Command |
|---|---|
| Install | `<install command>` |
| Run locally | `<run command>` |
| Test | `<test command>` |
| Single test | `<command for one test file>` |
| Lint and format | `<lint command>` |
| Build | `<build command>` |

## Layout

| Path | Holds |
|---|---|
| `<src/area/>` | <what lives there> |
| `docs/` | Implementation docs as an OKF bundle. Start at [docs/index.md](docs/index.md) |

## Rules

- <A rule agents must follow, linked to its convention doc.>
- Configuration comes from `<env file or secret store>`. Use variable names only; never commit values.

## Docs

| Before changing | Read |
|---|---|
| <code area> | [<doc title>](docs/<path>.md) |

When a task changes behavior, update the docs whose `sources` list the changed files once, at the end of the task. Add a new doc only for something someone will need later that the code doesn't show: a user-visible feature, a limit, a config option. Record a material choice in `docs/decisions/` when someone can state why. Don't document fixes, refactors or tests.
```
