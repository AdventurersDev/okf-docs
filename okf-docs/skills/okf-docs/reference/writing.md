# Writing

Every sentence carries a fact the reader needs or an instruction they follow. Cut the rest; keep every fact.

## Cut

| Pattern | Example | Instead |
|---|---|---|
| Filler openers | "It is important to note that", "In this guide we will" | Start with the fact |
| Hedging | "might potentially", "generally speaking", "basically" | State it, or state the condition: "Fails when the file exceeds 500 MB" |
| Hype | "seamless", "robust", "powerful", "leverage", "unlock", "cutting-edge" | Say what it does, with the number |
| Recap sections | "Conclusion" or "Summary" at the end, repeating the page | Delete. A long page gets one summary line at the top |
| Headings and bullets without facts | "Overview" with one vague sentence; "Benefits" listing adjectives | Merge or delete |
| Bold everywhere | Bold in every bullet | Bold only what a skimmer must not miss |
| Emoji headings, exclamation marks | "## 🚀 Getting started!" | "## Get started" |
| Chat leftovers | "Great question", "I hope this helps", "Feel free to" | Delete |
| "Not X, it's Y" | "It's not a cache, it's a ledger" | "It's a ledger: …" |
| The obvious | "The login page lets users log in" | Delete, or say what isn't obvious |

## Keep

Numbers, limits, defaults, units; names of commands, flags, fields and errors; edge cases and failure modes; examples; dates and owners. Unsure about a sentence? Ask what fact would be lost without it. If none, cut it.

## Debloat procedure

Use it for "debloat this" and before anything is published.

1. List the facts in the original, one line each.
2. Rewrite per the cuts above and the audience below.
3. Check that every listed fact survived; restore any that didn't.
4. Run `okf.py lint <file>` on the result. Fix true hits; ignore false ones.
5. Show the diff and the word count before and after. On a file outside a bundle, such as a README, don't add frontmatter unless asked.

## Audiences

| Reader | Wants | Shape |
|---|---|---|
| Agents (AGENTS.md, repo docs) | Exact commands, paths, rules, gotchas | Terse imperative lists, no narrative. Link to docs instead of copying them |
| Team | The current answer, fast | Summary line first. Tables for comparisons. Decisions with dates and owners |
| Public (help center, developer docs) | Finish a task or understand a concept | Task-first titles ("Export your data"); numbered steps, one action each; the expected result after the steps; tables for options; the site's `voice.md` for reader, tone and language (publish.md) |

## Visual presentation (public pages)

- One idea per page. The title names the task or the concept.
- Say what the reader can do first, then how.
- Steps are numbered and imperative, one action each, with UI labels in bold exactly as on screen.
- Tables for options, limits, plans and comparisons.
- A Mermaid diagram for a flow, state machine or architecture with more than three steps or actors. Keep it under about ten nodes.
- Where a screenshot would help, write `<!-- screenshot: what it shows -->` and list it in your report. Never describe UI you haven't seen.
- Callouts only for what loses data, costs money or blocks the task.

## The lint

`okf.py lint <paths>` counts filler, hedges, hype, chat leftovers, emoji headings, bold density, empty and recap sections, and long sentences, skipping code. It gives hints, not verdicts: "robust" can be a real property. Hits per 100 words let you compare before and after.
