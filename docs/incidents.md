# Agent-quality incidents

Wrong or misleading answers the agent gave a user: what happened, the cause and what now stops it. Privacy incidents are not recorded here; they go to the privacy register (see the cleverdragon WIKI → Incident register).

## 2026-10-27 — "anywhere in Europe" answered as zero results

**What the user saw.** Asked for "Homes for sale, anywhere in Europe", the agent said no listings were found, although Cubi holds thousands of matching homes. The answer also named an internal tool (`search_properties`).

**Cause.**
- Cubi's `search_properties` did not search. It asked a clarifying question (which country or region?), but the connector still opened that reply with "No properties matched…".
- `property_mcp/server.py` suppressed that line only for the `needs_location` facet, not for a reply that is just a question.
- The agent read the opening line and relayed it as a zero result. A genuine zero always carries Cubi's "Your search: … — no matches found." summary, or is filter_listings' bare "No properties matched these filters." with no question.

**Fixes.**
- `agent/reply_guard.py` (incoming and outgoing, `tests/test_reply_guard.py`):
  - **Incoming:** `classify()` labels every search reply as results, a genuine zero, a clarifying question, an error, or other. It keys on the reply's shape, not on the "No properties matched" line.
  - **Outgoing:** `guard_answer()` cuts any "no listings / nothing found" claim, in 7 languages, unless a reply this turn was a genuine zero. After a clarifying question, the claim is replaced by Cubi's question. It also strips raw markers (`<!-- CUBI_… -->`, `[searched with …]` headers) and bare portal ids outside links.
- `agent/guards.py`: `scrub_tool_names` strips internal tool names from the answer. It runs after `guard_answer`.
- `agent/loop.py`: an anywhere-search that comes back as a clarifying question falls back to per-market searches (`_per_market`, `why="asked_where"`), keyed on `kind == "clarify"`.
- Connector (cleverdragon `property_mcp/server.py`): `suppress_no_match` also covers a reply that is only a question, so Cubi stops prefixing clarifications with "No properties matched".

**Status.** `scrub_tool_names` and the fallback shipped in 6c49591. The reply guard is wired on top of them:
- every search reply, including each per-market one, is classified on Cubi's raw reply, before the agent's own screening;
- the fallback keys on `kind == "clarify"`;
- `guards.apply(…, replies=…)` runs `guard_answer` before `scrub_ids` and `scrub_tool_names`.

The zero-claim rule applies only in a turn that searched. "There are no homes on screen yet" is the agent's own state, not a claim about results. Tests: `tests/test_reply_guard.py`, and `tests/test_anywhere.py`, which covers the fallback with and without the old prefix and a genuine zero not being retried.
