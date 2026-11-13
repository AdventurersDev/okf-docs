# Presets: docs

Starting layouts for a repo's docs bundle ([kinds/docs](../reference/kinds/docs.md)). Init picks a preset from the signals, confirms it with the user, and creates only the folders that get a file now. A preset is a starting point: add or drop folders as the repo needs. When a repo fits two, such as an app with its backend in the same repo, start from the larger one and add the folders the other needs.

## library

**Signals:** a package manifest with public exports and a registry publish setup (npm, PyPI, crates.io, Maven, RubyGems); no server, deploy config or migrations.

| Folder | First files |
|---|---|
| `product/` | A concept per public capability |
| `system/` | `architecture.md`; `api/` with one file per public module or entry point; `conventions/` |
| `decisions/` | Material choices already made, only where someone can state the rationale |

Skip `operations/` and `security/` unless the library handles secrets or cryptography. AGENTS.md lists the build, test, lint and release commands.

## service

**Signals:** a server framework, a Dockerfile or deploy config (Kubernetes, Terraform, fly.toml, serverless), migrations, an OpenAPI, GraphQL or protobuf schema, environment config.

| Folder | First files |
|---|---|
| `product/` | A concept per user-visible feature |
| `system/` | `architecture.md`; `api/` with one file per resource group; `schema/` with one file per core model; `conventions/` |
| `operations/` | Deploy and rollback runbooks; `environments.md` |
| `security/` | Authentication, authorization and data handling |
| `decisions/` | Material choices already made |

AGENTS.md lists how to run it locally, test, migrate and deploy, and where environment config lives: variable names only, never values.

## app

**Signals:** a UI framework (React, Vue, Svelte, SwiftUI, Jetpack Compose, Flutter, Electron), screens or routes, a design system or design tokens, app store configuration.

| Folder | First files |
|---|---|
| `product/` | A concept per main feature, with its flows and states; `<feature>-design.md` for a design |
| `system/` | `architecture.md`; `schema/` for local data and storage; `conventions/` for UI rules |
| `operations/` | Release runbook, including store submission |
| `decisions/` | Material choices already made |

For the design system itself (tokens, components), link to its source or its DESIGN.md instead of copying it.

## monorepo

**Signals:** workspaces (pnpm, npm, yarn, Cargo, Go workspaces, Nx, Turborepo, Bazel).

- One root `docs/` bundle for what crosses packages: overall architecture, shared conventions, operations.
- A package gets its own bundle, `packages/<name>/docs/` with its own entry in config, only when it has its own users or its own deploy. The root bundle documents the other packages.
- The root AGENTS.md maps each package to its docs. A package with its own bundle may get its own AGENTS.md.
