---
name: compare-areas
description: Compare towns, cities or neighbourhoods on what living there is like — schools, public transport, safety, healthcare, beaches, cost of living — from cited web sources. Use when the user wants to choose between places, not to find or price homes.
---

# Compare areas from cited sources

1. Call `research_area` once with every place the user named (up to three), each with its country ("Valencia, Spain"), and up to three topics they care about, in English. If they named no topic, use schools, public transport and healthcare.
2. Answer in the user's language, side by side: one short paragraph per topic, each place's point followed by the number of the source it comes from, like [S2]. The app turns the numbers into links.

## Rules

- Only state what a returned source says. If the sources say nothing about a topic for a place, write that no source covered it. When they do cover it, say nothing about what they did not report. Never fill a gap from general knowledge.
- Never state a date or year the source excerpt doesn't state itself. If a source's date (shown after its site) is older than about three years, say so next to that point. Don't comment on undated sources; the app lists every source with its date under the answer.
- Don't pick a winner. You may say which place the sources favour on each topic the user named.
- Area research doesn't search homes. If the user wants homes in one of the places, offer to search them.
