# sync (Code module)

Bring the repo docs up to date with the code.

1. **Range:** the ref the user gave; otherwise the last **Sync** entry in the docs `log.md` (the script finds it); otherwise ask, defaulting to the last 20 commits. Uncommitted changes are included.
2. **Find:** `okf.py stale --since <ref> --json` lists the docs whose cited sources changed (affected) and the changed files no doc cites (uncovered). If it can't compare (no repository, or git didn't run), say why in one line and fall back to `okf.py stale --json` without `--since`: its re-check queue lists docs whose sources changed after they were last checked, by file times. Work from that queue, and skip step 3's diff: read each changed source instead.
3. **Read the change:** `git diff <ref> -- <source>` for each affected source. For each doc, decide: no impact (add an `okf-docs/<version>` `verified` entry, since you checked it), update, deprecate, or delete per lifecycle.md.
4. **Uncovered files:** write a new doc only when the change adds or alters behavior someone needs to know: an endpoint, a limit, a config option, a migration. Most uncovered files need nothing.
5. **Decisions:** for a material choice visible in the diff with no record, ask the user in one line whether to record it and why it was made. Write it only with their rationale; never infer one.
6. **AGENTS.md:** update it when commands, layout or conventions changed.
7. **Finish:** `okf.py index --write`, then `okf.py log <docs bundle> Sync "Synced to <short-sha>: <what changed>"`, then `okf.py check`.
8. **Commit:** ask first. Commit only the docs paths and `AGENTS.md`, apart from code, with the message `docs: sync to <short-sha>`.
