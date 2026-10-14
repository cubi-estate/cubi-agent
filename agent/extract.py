"""NL request → SearchFilter, by Nemotron, with validation, one repair retry and routing.

Routing is deterministic (agent/normalize.py), not the model's
`needs_free_text_search` flag: the eval showed Super raising it on plain city
searches. A request goes to the structured `filter_listings` path when a place
is named and nothing in the user's words needs free text (a region, "near the
beach", "quiet"); otherwise it falls back to the connector's free-text
`search_properties` (which runs Cubi's own server-side language model).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from . import lang as langmod
from . import llm
from . import normalize
from .schema import SearchFilter, strict_json_schema

EXTRACT_ROLE = os.environ.get("EXTRACT_ROLE", "super")

SYSTEM = (
    "You turn a home-search request into a search filter for a European property "
    "search service. Fill every field; use null or an empty list when the user did "
    "not say. Prices are in EUR; '400k' means 400000. Portuguese 'T1/T2/T3' means "
    "1/2/3 bedrooms; Spanish 'piso' and Portuguese 'apartamento' mean apartment; "
    "'moradia', 'chalet', 'Haus', 'maison', 'huis' mean house. Keep place names as "
    "the user wrote them. Reply with the JSON object only."
)
FOLLOW_UP = (
    "The user is refining an earlier search. Current filter:\n{current}\n"
    "Return the complete updated filter: keep what the user did not change, apply "
    "what they changed, drop what they asked to drop."
)


@dataclass
class Extraction:
    filter: SearchFilter | None
    route: str  # "filter" | "search"
    model: str
    latency_s: float
    attempts: int
    usage: dict = field(default_factory=dict)
    error: str | None = None


def _strip(s: str) -> str:
    s = re.sub(r"(?s)<think>.*?</think>", "", s or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    return (m.group(1) if m else s).strip()


route_for = normalize.route_for


def extract(message: str, current: SearchFilter | None = None, role: str | None = None, cli=None) -> Extraction:
    cli = cli or llm.client()
    model = llm.model(role or EXTRACT_ROLE)
    system = SYSTEM
    if current is not None:
        system += "\n\n" + FOLLOW_UP.format(current=current.model_dump_json())
    messages = [{"role": "system", "content": system}, {"role": "user", "content": message}]
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "SearchFilter", "schema": strict_json_schema(), "strict": True},
    }
    usage = {"in": 0, "out": 0}
    t0 = time.monotonic()
    error = None
    for attempt in (1, 2):
        try:
            r = cli.chat.completions.create(
                model=model, messages=messages, response_format=response_format,
                temperature=0, max_tokens=1024, extra_body=llm.NO_THINK,
            )
        except Exception as e:  # network/API error: degrade to free-text search
            error = f"{type(e).__name__}: {str(e)[:200]}"
            break
        if r.usage:
            usage["in"] += r.usage.prompt_tokens or 0
            usage["out"] += r.usage.completion_tokens or 0
        content = r.choices[0].message.content or ""
        try:
            f = SearchFilter.model_validate_json(_strip(content))
        except ValidationError as e:
            error = f"invalid output: {e.error_count()} errors"
            messages += [
                {"role": "assistant", "content": content[:2000]},
                {"role": "user", "content": "That did not match the schema: "
                 + json.dumps(e.errors(include_url=False)[:3], default=str)[:800]
                 + ". Reply with the corrected JSON object only."},
            ]
            continue
        f.lang = langmod.detect(message, default=current.lang if current else "en")
        f = normalize.apply(f, message, current)
        return Extraction(f, route_for(f), model, round(time.monotonic() - t0, 2), attempt, usage)
    return Extraction(None, "search", model, round(time.monotonic() - t0, 2), 2, usage, error)
