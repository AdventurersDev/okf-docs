# Lifecycle

How files change, get replaced, decay and get deleted. Two goals: a reader never finds two versions of the truth, and nothing true gets lost.

## When something changes

| Situation | Do |
|---|---|
| The facts in a file changed | Edit it in place. Bump `generated.at` and remove `verified` entries, unless the person confirming re-checked. Git keeps the old version |
| A file was replaced by another file (merged, split, renamed) | Delete the old file, repoint inbound links, regenerate the index, log a **Deletion** that names the replacement |
| The thing a file describes is deprecated but still exists, such as an API version still served | Keep the file with `status: deprecated` and `superseded_by` pointing to the replacement. Delete it once the thing is gone |
| A decision was overturned | Never delete it. The new decision gets `supersedes`; the old one gets `status: deprecated` and `superseded_by`; each links the other |
| An observation was promoted to a fact (brain) | Delete the observation. The canonical file carries its `sources` forward |
| An observation was contradicted, or is past its `stale_after` | Delete it and log the reason |
| A raw asset file is past `retention.raw_files` | Delete the raw file. Keep its metadata file and summary, which other files cite |

Safeguards:

- Deletions are proposed (check does this) and carried out only after the user approves the list. Each one is logged; in git, commit deletions apart from other changes.
- Without git there is no undo. Set `status: deprecated` instead of deleting, and say so.
- Before deleting, find inbound links (search the bundle for the filename) and fix each one.
- After deleting, run `okf.py index --write`. It drops the entries of deleted files and of folders left without docs. A folder left with only `index.md` or `log.md` goes too, in the same approved list; check reports it until it's gone.

## Trust and verification

The trust tier comes from `verified` (OKF §5.3): no entry is **unverified**; entries only from tools or processes are **machine-confirmed**; any `human:` entry is **human-reviewed**.

- Add a `human:` entry only when that person confirmed the current content in this session: they said it's right, or approved it in the review queue.
- Add an `okf-docs/<version>` entry when you checked the content against its cited sources yourself (you read the code and it matches). That resets decay but stays machine-confirmed.
- When facts change, remove the existing entries; they confirmed the old content.

## Staleness and decay

A file is stale now when:

- `now >= stale_after`;
- a cited local source changed after the file's last check (git commit time, or file time outside git); or
- it is a published page and one of its sources is stale or changed after the page was verified.

Soft decay: a file's weight halves every half-life, counted from the latest `verified.at`, or from `generated.at` if it was never verified. Half-lives come from config `decay`, looked up by `type`, then `class`, then `default`. Defaults: 12 months; observations 3 months; runbooks 6 months; decisions, assets, releases and updates never decay, because they record a moment.

`okf.py stale` lists the re-check queue: stale files first, then files past one half-life. A re-check either confirms the file (add a `verified` entry) or changes it.

## Ranking

Use for `ask` and for choosing which file to update. Apply in order; each step breaks ties from the one before.

1. **Scope:** the asked scope, then its parent, then the root. Never a sibling.
2. **Type fit:** concept or canonical for "what is", decision for "why", runbook for "how do I operate it", observation or asset for "what have we seen".
3. **Relevance:** does it answer the question.
4. **Trust:** human-reviewed, then machine-confirmed, then `reported`, then `inferred`. Files marked `draft` by another tool last.
5. **Specificity fit:** the file whose `specificity` matches the question wins. "What is the export size limit" wants `exact`; "what is export for" wants `general`. Never length: a long transcript doesn't outrank a one-line fact.
6. **Decay:** higher current weight wins. Decisions don't decay for "why" questions. Deprecated files are out unless the question is about history.
7. **Corroboration:** prefer claims backed by more independent sources. When files disagree, show both and say which is newer and better verified.

## Promotion (brain)

An observation becomes canonical when a human confirms it, when two or more independent sources support it and nothing contradicts it, or when a decision makes it so. Write or update the canonical file with the observation's sources, then delete the observation. One customer's statement stays an observation, however detailed.
