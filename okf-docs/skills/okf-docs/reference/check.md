# check

Audit the bundles, fix what is mechanical, and turn everything else into decisions for the user.

## Run

1. `okf.py check --json`, on all bundles or on the path given.
2. `okf.py stale --json` for the re-check queue.
3. `okf.py upgrade --dry-run` when the context output reported `UPGRADE`.

Some checks need reading, not the script: contradictions between files; implementation detail in the brain or business content in repo docs; one subject covered twice under different titles; decisions mentioned in `log.md` without a decision record. Read the files involved.

## Report

Lead with counts, then the findings that need the user, in this order:

1. **OKF errors** (non-conformant), then OKF warnings. Fix these first.
2. **House issues:** naming, titles, descriptions, index coverage.
3. **Content:** broken links, stale, unverified or `verification-outdated` files, duplicates, bloat, knowledge in the wrong layer; overdue actions (`action-overdue`: say who owns each).
   Tracker files: `tracker-format` means the Open table is missing or its header is wrong; fix it. `tracker-prune` lists old Done or Answered rows; propose removing them.
4. **Deletion candidates**, each with the lifecycle.md case that applies.
5. **Format upgrades** available.

## Fix

- **Without asking** (mechanical, no change in meaning): `okf.py check --fix`, which regenerates indexes (keeping the root frontmatter), adds a missing `log.md`, drops frontmatter from `log.md` and sets `okf_version`; links whose target moved, when the new path is unambiguous; misspelled keys. Not while files are in the old format: propose the upgrade first, and fix only after it's approved and done, so the user sees one set of changes.
- **After asking**, as one numbered list the user can approve in one reply: content edits, merges, deletions, the format upgrade with its `index-page` moves and the `LEGACY_RULES` files to retire ([format](format.md), "Upgrading"), moving knowledge between repo docs and the brain.
- **After approved deletions:** delete the files, and any folder they leave with only `index.md` or `log.md` (list those folders in the approval too). Fix inbound links, run `okf.py index --write` so no index lists what is gone, then `okf.py log <bundle> Deletion "<what and why>"`. If the user wants a commit, commit the deletions apart from other changes.

## Brain review

For `/okf-docs check brain`, "review the brain", or the `BRAIN_REVIEW` signal. It turns inputs into confirmed knowledge. Read first, write nothing before approval, and present one numbered list the user approves in one reply:

1. **Promotion candidates:** observations backed by two or more independent sources (lifecycle.md, Promotion): `promotion-candidate` findings, and themes across recent assets. Name the canonical file and propose its wording.
2. **Conflicts:** assets and observations newer than a canonical file's `generated.at` that contradict it. Propose the update, or a question for the owner.
3. **Duplicates:** one customer, person, product or initiative filed in two places (`duplicate-title` plus judgment). Propose a merge.
4. **Open questions** that newer assets or answers now settle: write the answer, move the row to Answered.
5. **Missing history lines** (`## History`, write.md) for entities that recent assets are about.
6. **The usual brain items:** stale observations, deletion candidates, tracker pruning.
7. **Tickets** (with `brain.tickets`): Open actions whose ticket is closed, to move to Done (lifecycle.md, Trackers), and `action-unsynced` actions to sync (write.md, Tickets).

After the approved changes, `okf.py log <brain> Review "<what was proposed and applied>"`. That entry resets the `BRAIN_REVIEW` count.

## Review queue

For unverified files and the stale list, show each file's title, a one-line summary of its claims, and its sources. Ask the user to confirm, correct or skip each one, or to confirm the whole batch at once; keep batches to five to ten files.

- **Confirmed:** add an entry to `verified` with `by: <human ACTOR>`, `at: <NOW>` and `x-okfdocs-via: review` (if no human id is set, ask for it first; lifecycle.md), in block style (format.md), and remove `status: draft` if another tool set it.
- **Corrected:** edit the file, then verify it.

Don't repair format drift as a side effect of other commands. Report it and leave it to check.
