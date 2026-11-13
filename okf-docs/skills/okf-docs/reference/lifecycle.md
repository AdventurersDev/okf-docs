# Lifecycle

How files change, get replaced, decay and get deleted. Two goals: a reader never finds two versions of the truth, and nothing true gets lost.

## When something changes

| Situation | Do |
|---|---|
| The facts in a file changed | Edit it in place and bump `generated.at`. Keep the old `verified` entries as history; they stop counting. Git keeps the old version |
| A file was replaced by another file (merged, split, renamed) | Delete the old file, repoint inbound links, regenerate the index, log a **Deletion** that names the replacement. If the old path may be referenced from outside the bundle (a published URL, another repo, another project's `AGENTS.md`), leave a short stub there with `status: deprecated` and `superseded_by` |
| The thing a file describes is deprecated but still exists, such as an API version still served | Keep the file with `status: deprecated` and `superseded_by` pointing to the replacement. `superseded_by` means something only with `status: deprecated`. Delete it once the thing is gone |
| A decision was overturned | Never delete it. The new decision gets `x-okfdocs-supersedes`; the old one gets `status: deprecated` and `superseded_by`; each links the other |
| An observation was promoted to a fact (brain) | Set `status: deprecated` and `superseded_by` on the observation, then delete it once the user approves. The canonical file carries its `sources` forward |
| An observation was contradicted, or is past its `stale_after` | Delete it and log the reason |
| A raw asset file is past `retention.raw_files` | Delete the raw file. Keep its metadata file and summary, which other files cite |

Safeguards:

- Deletions are proposed (check does this) and carried out only after the user approves the list. Each one is logged; in git, commit deletions apart from other changes.
- Without git there is no undo. Set `status: deprecated` instead of deleting, and say so.
- Before deleting, find inbound links (search the bundle for the filename) and fix each one.
- After deleting, run `okf.py index --write`. It drops the entries of deleted files and of folders left without docs. A folder left with only `index.md` or `log.md` goes too, in the same approved list; check reports it until it's gone.

## Trust and verification

The trust tier comes from the current `verified` events (OKF §5.3). An event is current when its `at` is on or after `generated.at` (or there is no `generated.at`). Older events are history and don't count.

- **Human-reviewed:** a current event from a `human:` actor.
- **Machine-confirmed:** current events, none from a human (`team:`, `process:`, tools).
- **Unverified:** no current event. When events exist but none is current, say "verified before the last change" (check: `verification-outdated`); it joins the review queue.

Where content came from is not a tier. It is in `sources`: an entry with `author: "human:<id>"` means that person stated it ("stated by Pat in the 2026-11-20 call"), and a file with no sources says in its body what it was inferred from. Inside a tier, a file with sources ranks above one without.

- Add a `human:` entry only when that person confirmed the current content in this session: they said it's right (`x-okfdocs-via: chat`), or approved it in the review queue (`x-okfdocs-via: review`). The entry is a record of what they said here, not a signature; git shows who committed it.
- The id comes only from `OKF_ACTOR` or `git config okf.actor`. If `okf.py now` prints "human: not set", ask the person for their id; when it shows a suggestion from `git user.name`, offer that as the first answer. Once they confirm, offer to save it with `git config --global okf.actor <id>` and run that only after they agree, so the question comes once per machine. Never write an id they haven't confirmed, and never take one from the login name or email.
- Add an `okf-docs/<version>` entry when you checked the content against its cited sources yourself (you read the code and it matches). That resets decay but stays machine-confirmed.
- When facts change, bump `generated.at` instead of deleting entries; they confirmed the old content and stop counting.

## Staleness and decay

A file is stale now when:

- `now >= stale_after`, or `stale_after` doesn't parse (check: `stale-after-format`);
- a cited local source changed after the file's last check (git commit time, or file time outside git); or
- it is a published page and one of its sources is stale or changed after the page was verified.

Soft decay: a file's weight halves every half-life, counted from the latest current `verified.at`, or from `generated.at` if it was never verified. Half-lives come from config `decay`, looked up by `type`, then `class`, then `default`. Defaults: 12 months; observations 3 months; runbooks 6 months; decisions, assets, releases and updates never decay, because they record a moment.

`okf.py stale` lists the re-check queue: stale files first, then files past one half-life. A re-check either confirms the file (add a `verified` entry) or changes it.

## Ranking

Use for `ask` and for choosing which file to update. Apply in order; each step breaks ties from the one before.

1. **Scope:** the asked scope, then its parent, then the root. Never a sibling.
2. **Type fit:** concept or canonical for "what is", decision for "why", runbook for "how do I operate it", observation or asset for "what have we seen".
3. **Relevance:** does it answer the question.
4. **Trust:** human-reviewed, then machine-confirmed, then unverified (current events only); inside each, a file with sources before one without. Files marked `draft` by another tool last.
5. **Specificity fit:** the file whose `x-okfdocs-specificity` matches the question wins. "What is the export size limit" wants `exact`; "what is export for" wants `general`. Never length: a long transcript doesn't outrank a one-line fact.
6. **Decay:** higher current weight wins. Decisions don't decay for "why" questions. Deprecated files, and files with an unknown `status`, are out unless the question is about history.
7. **Corroboration:** prefer claims backed by more independent sources.

**When files disagree,** prefer in this order; the first difference decides: (1) a current file (`status` stable or draft, not deprecated or unknown); (2) a higher trust tier (human-reviewed, machine-confirmed, then unverified); (3) not stale; (4) the later `generated.at`. Tell the user about the conflict and which file you preferred.

## Trackers (brain)

`actions.md` and `questions.md` (class `tracker`) are living lists, not knowledge claims. They have no `sources`, no verification, no decay and no review-queue entry.

- An action moves from Open to Done, with today's date in `Done`, when the user says it is done.
- With `brain.tickets`, an action with a ticket link is done when its ticket is: in the brain review, or when the user asks about actions, look up each Open action's ticket with the connector and propose moving the closed ones to Done, with the ticket's close date. A cancelled ticket: ask. Never change a ticket from the brain; when the user marks an action done whose ticket is still open, ask whether to close the ticket too and do it only on their OK.
- A question moves from Open to Answered when its answer has been written into a file; link that file in "Answer in".
- Done and Answered rows older than 90 days are proposed for removal as a list, like deletions (`tracker-prune`).

## Promotion (brain)

An observation becomes canonical when a human confirms it, when two or more independent sources support it and nothing contradicts it, or when a decision makes it so. Write or update the canonical file with the observation's sources, then retire the observation as in the table above. One customer's statement stays an observation, however detailed.

Promotion happens in the brain review (check.md): check reports `promotion-candidate` for observations with two or more sources, and the user approves each promotion in the review's list.

## History lines (brain)

Entity files carry a `## History` section with one line per meeting, decision or observation about them. Adding a line is not a change of meaning: it does not bump `generated.at`, so verifications stay current. Add lines with `okf.py history` (format.md), which touches nothing else. Any other edit to a verified file either bumps `generated.at` or is trivial; in git, check flags a changed text with an unmoved `generated.at` (`generated-not-bumped`).
