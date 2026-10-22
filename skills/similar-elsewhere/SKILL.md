---
name: similar-elsewhere
description: Show homes like one listing the user is looking at, in another city, side by side with it — asking prices, features as the listings state them, environment readings, distances and climate. Use when the user asks for something similar to a home on screen, in a different place.
---

# Similar homes in another city

1. Call `find_similar_elsewhere` with the listing the user means (the app resolves card numbers like "#2" itself) and the city they named. If they named no city, ask which city to look in; don't pick one.
2. The app shows the result as a table with the matches as numbered cards. Answer in the user's language in two or three sentences: the asking prices side by side, then one or two differences that matter (a feature one listing states and the other doesn't, an environment reading, a distance).

## Rules

- Only state figures the result gives.
- These are asking prices. Never call a difference a saving, a bargain, a premium or a valuation.
- "not stated" means the listing doesn't say; "unknown" means there is no reading. Never turn either into "it has no …".
- If there is no match, say that no listing with the same bedrooms and a similar size was found there, and offer another city. Don't suggest a looser match.
- Don't pick a winner or say which home to buy.
