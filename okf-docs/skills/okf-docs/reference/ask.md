# ask

Answer from the bundles, read-only, with citations. Don't edit files here; if the answer should be written down, offer `write`.

1. **Scope:** what the question is about (a product, an area, a customer, the team) and which layer it belongs to: implementation (repo docs) or business (brain).
2. **Find candidates** with `okf.py find <words>`, or walk `index.md` from the bundle root down to the relevant folder. For a large or unfamiliar bundle, give the `okf-docs:okf-reader` agent the question and the bundle path (Lookup mode).
3. **Rank** per lifecycle.md: scope, type fit, relevance, trust, specificity fit, decay, corroboration.
4. **Read** the top candidates in full. Follow their links one level when the answer needs it, and open sources only to settle a doubt.
5. **Answer** first, then link the files it came from. Add a short trust note when it matters: "unverified", "inferred, not stated by a source", "last verified 14 months ago", "a cited source changed since", "draft". When files disagree, show both and say which is newer and better verified.
6. **Gaps:** if the bundles don't answer it, say so plainly. Then answer from the code or other sources if you can, marked as not from the docs, and offer to record it.

History questions ("when did we change X", "what was it before"): read `log.md` first, then `git log -p -- <file>` on the doc. Why questions: read the decisions, including deprecated ones, which explain the history.
