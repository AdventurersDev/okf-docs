# check

Audit the bundles, fix what is mechanical, and turn everything else into decisions for the user.

## Run

1. `okf.py check --json`, on all bundles or on the path given.
2. `okf.py stale --json` for the re-check queue.
3. `okf.py upgrade --dry-run` when the context output reported `UPGRADE`.

Some checks need reading, not the script: contradictions between files; implementation detail in the brain or business content in repo docs; one subject covered twice under different titles; decisions mentioned in `log.md` without a decision record. Read the files involved.

## Report

Lead with counts, then the findings that need the user, in this order:

1. **OKF errors** (spec breaks). Fix these first.
2. **House issues:** naming, titles, descriptions, index coverage.
3. **Content:** broken links, stale or unverified files, duplicates, bloat, knowledge in the wrong layer.
4. **Deletion candidates**, each with the lifecycle.md case that applies.
5. **Format upgrades** available.

## Fix

- **Without asking** (mechanical, no change in meaning): `okf.py check --fix`, which regenerates indexes and adds a missing `log.md` and `okf_version`; links whose target moved, when the new path is unambiguous; misspelled keys. Not while files are in the old format: propose the upgrade first, and fix only after it's approved and done, so the user sees one set of changes.
- **After asking**, as one numbered list the user can approve in one reply: content edits, merges, deletions, the format upgrade with its `index-page` moves and the `LEGACY_RULES` files to retire ([format](format.md), "Upgrading"), moving knowledge between repo docs and the brain.
- **After approved deletions:** delete the files, and any folder they leave with only `index.md` or `log.md` (list those folders in the approval too). Fix inbound links, run `okf.py index --write` so no index lists what is gone, then `okf.py log <bundle> Deletion "<what and why>"`. If the user wants a commit, commit the deletions apart from other changes.

## Review queue

For unverified files and the stale list, show each file's title, a one-line summary of its claims, and its sources. Ask the user to confirm, correct or skip each one; keep batches to five to ten files.

- **Confirmed:** add an entry to `verified` with `by: <human ACTOR>` and `at: <NOW>`, in block style (format.md), and remove `status: draft` if another tool set it. Keep `credibility`.
- **Corrected:** edit the file, then verify it.

Don't repair format drift as a side effect of other commands. Report it and leave it to check.
