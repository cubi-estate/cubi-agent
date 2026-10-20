---
name: compare-areas
description: Compare towns, cities or neighbourhoods on what living there is like — schools, public transport, safety, healthcare, beaches, cost of living — from cited web sources. Use when the user wants to choose between places, not to find or price homes.
---

# Compare areas from cited sources

1. Call `research_area` once with every place the user named (up to three) and the topics they care about, in English. If they named no topic, use schools, public transport and healthcare.
2. Answer side by side, one short paragraph or table row per topic, each place's point followed by its source link exactly as returned and its date when given.

## Rules

- Only state what a returned source says. If the sources say nothing about a topic for a place, write that no source covered it. Never fill a gap from general knowledge.
- Say how recent the sources are; flag anything older than about three years or undated.
- Don't pick a winner. You may say which place the sources favour on each topic the user named.
- Area research doesn't search homes. If the user wants homes in one of the places, offer to search them.
