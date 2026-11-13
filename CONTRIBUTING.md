# Contributing

## Tests

```
python3 -m unittest discover tests
claude plugin validate ./okf-docs
```

The tests use only the standard library; with PyYAML installed, one more test compares `okf.py`'s YAML reader with it. CI runs them on Linux, Windows and macOS (`.github/workflows/test.yml`). They copy the fixtures in `okf-docs/evals/fixtures/` to a temporary folder; the evals use the same fixtures. Before a release, also run the manual checks in [TESTING.md](TESTING.md) on each OS.

## Evals

The [eval suite](https://code.claude.com/docs/en/plugin-evals) in `okf-docs/evals/` gives Claude fourteen tasks with the plugin loaded and grades what it did: whether the skill fired, which files it wrote, and what they contain. Each case's `scaffold.sh` seeds the run's empty workspace from a fixture.

| Case | Passes when |
|---|---|
| `status-menu` | `/okf-docs` in a project without docs suggests init and changes nothing |
| `init-plans-first` | Init reports what it found, asks or proposes a plan, and writes nothing before approval |
| `record-decision` | The decision gets number 003 and only the stated reasons; 002 is kept, deprecated and linked both ways; the export doc, index and log are updated |
| `ask-why` | The answer comes from both decision records, cites them, and edits nothing |
| `debloat-readme` | Hype, filler and emoji headings are gone, every fact stays, and no frontmatter or config is added |
| `check-proposes-deletions` | Both deletion candidates are proposed with reasons, and nothing is deleted |
| `document-code` | A new doc cites `src/auth/session.ts`, states the 12-hour expiry, and claims no human review |
| `ingest-meeting` | The notes become an asset and an expiring observation that cites it; the contact's phone number is written nowhere |
| `no-trigger-code-change` | A code change in a project without OKF docs doesn't start the skill |
| `refactor-no-new-docs` | A rename in a project with docs changes the code and writes no docs |
| `sync-limit-change` | After a commit raises the export limit, sync updates the doc, clears its old verification, deals with the help page, logs the sync and commits nothing |
| `publish-asks-voice` | The first page for a help center without `voice.md` starts with at most three questions on reader, tone and language, and writes no page |
| `publish-help-page` | With `voice.md`, the page is public, marks its credibility, has no draft status, cites the export doc, states the limit, claims no review, and goes to the user for sign-off |
| `upgrade-legacy` | Check on docs from the older okf skills offers an upgrade with its changes, proposes retiring the old skill copy in `.claude/skills`, and changes nothing |

Run the suite from the repository root, with Claude Code 2.1.269 or later and git 2.31 or later:

```
claude plugin eval ./okf-docs --scaffold --allow-tools Write Edit "Bash(python3 *)"
```

`--scaffold` runs the setup scripts. The grant lets Claude write files and run `okf.py`, inside Claude Code's sandbox.

Every run is billed to your account. On the default model, one run of a case with the plugin cost $0.13 (`status-menu`) to $0.56 (`ingest-meeting`), about $3.65 for all fourteen. By default each case runs three times with the plugin and three times without it, to measure what the plugin adds, so the full suite is 84 runs. While you iterate, run the smoke cases once, with the plugin only:

```
claude plugin eval ./okf-docs --tag smoke --runs 1 --ablation none --scaffold --allow-tools Write Edit "Bash(python3 *)"
```

`--case <name>` runs one case; it takes a single name or glob, and a second `--case` replaces the first. In CI, add `--trust-plugin`, `--threshold 0.8` and `--max-cost-usd <limit>`, and pin `--model`. Results go to `okf-docs/evals/results/`, which git ignores.
