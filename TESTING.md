# Testing a release by hand

Run these on each OS before a release, in a throwaway copy of a real repository. Every step names what should happen.

## Install

1. Unzip the release, open a terminal in a repository, and start `claude`.
2. `/plugin marketplace add <unzipped folder>`, then `/plugin install okf-docs@waybound`, then restart Claude Code.
3. `/plugin` lists okf-docs as installed and enabled.

## Python

4. In a terminal, run `python3 --version`, `python --version` and `py -3 --version`. Note which ones print 3.8 or later.
5. `/okf-docs` replies with a short status and no Python error. If only `python` or `py` works, Claude should switch to it without asking.

## Commands

6. `/okf-docs init`: it reports what it found and asks or proposes a plan. Approve it. It writes `.okf/config.yaml`, `docs/` and `AGENTS.md`.
7. Open `docs/index.md` in an editor that shows line endings: LF, not CRLF. Titles with non-ASCII letters (æ, ø, å, é) show correctly.
8. "Record this decision: we use Postgres for all new services, because the team knows it." It writes `docs/decisions/001-….md` and adds it to the index and `docs/log.md`.
9. "What did we decide about databases?" The skill fires, and the answer cites the decision file.
10. `/okf-docs check`: no OKF errors. Links in indexes use `/`, never `\`.
11. "Debloat README.md." The facts stay, the filler goes, and it reports word counts.

## Hooks

Hooks run in Git Bash on Windows, which Claude Code already uses there.

12. Start a new session in the project and ask "what do you know about this project's docs?" Claude mentions the OKF docs and the okf-docs skill without reading any files: that's the session hook.
13. Set `hooks.edits: true` in `.okf/config.yaml` and restart. Ask Claude to change a source file that a doc lists in `sources`. After the edit, Claude mentions that doc once.

## Checker without Claude

14. From the unzipped folder: `python -m unittest discover tests` (or `python3`/`py -3`). All tests pass; one may be skipped.
15. `python okf-docs/skills/okf-docs/scripts/okf.py check --project <repo>` prints findings and exits with 0, or 1 if there are OKF errors.

Report the OS, Claude Code version (`claude --version`), Python command that worked, and the first step that went wrong.
