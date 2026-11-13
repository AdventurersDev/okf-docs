# Routing: the bare call

Used when `/okf-docs` runs with no argument. Show status and suggestions, then stop. Never start a command from here; the user picks.

## Status

At most four lines, from the context output, leaving out any line with nothing to report:

- bundles with file counts and files to review, for example `docs/ 42 files (3 to review)`;
- open findings: OKF errors, house issues, stale, unverified;
- date of the last log entry;
- modules that are on.

With `NO_CONFIG` and no bundles, the status is one line: there are no OKF docs here yet.

## Suggestions

Offer two or three, most useful first. Each is one line: an exact command from the commands table, or a plain request such as "debloat README.md", and what it does in a few words.

| Signal in the context output | Suggest |
|---|---|
| `NO_CONFIG` | `/okf-docs init`, saying what it will scan |
| `CONFIG_ERROR` | Fixing `.okf/config.yaml`, quoting the error |
| `LEGACY_SKILLS`, or your skill list shows an `okf-docs` or `okf-company-brain` skill that isn't this plugin's | Removing the old standalone skills (name them) |
| `UPGRADE` | `/okf-docs check` to upgrade files in an older format |
| OKF errors | `/okf-docs check` |
| `SYNC` (code changed since the last sync) | `/okf-docs sync` |
| `ACTIONS` (overdue actions) | Name the overdue count in the status; suggest asking who owns them |
| `TICKETS_PENDING` (open actions with no ticket) | Syncing them to the ticket system (write.md, Tickets) |
| `BRAIN_REVIEW` (assets added since the last review) | `/okf-docs check brain` to promote, reconcile and merge |
| `QUESTIONS` (open questions in the brain) | `/okf-docs write` to go through them |
| Review queue (unverified, past half-life) | `/okf-docs check` to work through the queue |
| This conversation produced knowledge that isn't in the docs | `/okf-docs write` to capture it |
| Publish on and pages stale | `/okf-docs publish` to refresh them |
| Nothing pending | `/okf-docs ask` with an example question from the bundle |

## Workflow questions

"What can this do?" or "Which command?": answer from the commands table in SKILL.md in two or three sentences. Don't run anything.
