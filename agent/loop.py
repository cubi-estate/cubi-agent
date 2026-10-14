"""The agent: one conversation, a Nemotron tool loop, deterministic guards.

Per turn:
  1. language is detected in code; a skill is picked by keyword rule;
  2. Nemotron (the loop model) runs with that skill's SKILL.md as its system
     prompt and only that skill's tools, for at most MAX_STEPS tool calls;
  3. `search_homes` is local: a second Nemotron call extracts a structured filter
     (keeping the conversation's current filter for refinements) and code routes
     it to `filter_listings`, or to the connector's free-text search if no town
     or city was given;
  4. the answer passes URL, contact-detail and price-wording guards.

`turn()` yields events — {"type": "action" | "answer", ...} — so the CLI and the
web server can show a short action log (never raw model reasoning).
"""
from __future__ import annotations

import json
import os
import time
from typing import Iterator

from . import extract as extractmod
from . import guards, lang as langmod, llm, skills as skillsmod
from .mcp_client import CubiMCP, MCPError
from .schema import SearchFilter

MAX_STEPS = 5
TOOL_TEXT_CAP = 12000
HISTORY_TOOL_CAP = 1500
LOOP_ROLE = os.environ.get("LOOP_ROLE", "super")
LOOP_THINKING = os.environ.get("LOOP_THINKING", "off") == "on"

SEARCH_HOMES_TOOL = {
    "type": "function",
    "function": {
        "name": "search_homes",
        "description": (
            "Search Cubi Estate's listings of homes for sale or rent in Europe. Pass the "
            "user's request in their own words, including refinements such as 'only with a "
            "pool' or 'up to 500k instead'; the current search filter is kept automatically. "
            "Returns listings with their URLs and ids."
        ),
        "parameters": {
            "type": "object",
            "properties": {"request": {"type": "string", "description": "The user's request, verbatim or lightly condensed."}},
            "required": ["request"],
        },
    },
}

BASE_RULES = (
    "You are Cubi, a home-search assistant for Europe, running on an open model. "
    "Answer in the user's language ({lang}). Be brief: a one-line summary of what was "
    "searched, then the homes as a short list (price, place, size, bedrooms, one or two "
    "matching features, and the listing URL exactly as returned). Only describe homes the "
    "tools returned. Never invent URLs, ids, prices or contact details.\n"
    "In this app the skill's `filter_listings` and `search_properties` are both reached "
    "through `search_homes`, which chooses between them; call `search_homes` for any new "
    "or refined search, and `get_listing` for one home's details."
)


def _describe(f: SearchFilter) -> str:
    bits = [f.transaction_type]
    if f.type:
        bits.append("/".join(f.type))
    if f.min_bedrooms:
        bits.append(f"{f.min_bedrooms}+ bed")
    if f.max_price:
        bits.append(f"≤ €{f.max_price:,.0f}" + ("/month" if f.transaction_type == "rent" else ""))
    if f.features:
        bits.append("+".join(f.features))
    if f.has_parking:
        bits.append("parking")
    if f.location:
        bits.append("in " + ", ".join(f.location))
    return " · ".join(bits)


class Agent:
    def __init__(self, mcp: CubiMCP | None = None, cli=None, limit: int = 6):
        self.mcp = mcp or CubiMCP()
        self.cli = cli or llm.client()
        self.skills = skillsmod.load()
        self.limit = limit
        self.history: list[dict] = []
        self.filter: SearchFilter | None = None
        self.has_results = False
        self.lang = "en"
        self.stats = {"llm_in": 0, "llm_out": 0, "fallback_searches": 0, "filter_searches": 0}

    # ---- tools -------------------------------------------------------------
    def _tools_for(self, skill: skillsmod.Skill) -> list[dict]:
        mcp_names = [t for t in skill.tools if t != "search_homes"]
        tools = self.mcp.openai_tools(mcp_names) if mcp_names else []
        if "search_homes" in skill.tools:
            tools.insert(0, SEARCH_HOMES_TOOL)
        return tools

    def _search_homes(self, request: str) -> Iterator[dict | str]:
        ex = extractmod.extract(request, current=self.filter, cli=self.cli)
        self.stats["llm_in"] += ex.usage.get("in", 0)
        self.stats["llm_out"] += ex.usage.get("out", 0)
        if ex.filter is not None and ex.route == "filter":
            self.filter = ex.filter
            self.stats["filter_searches"] += 1
            yield {"type": "action", "text": f"Understood: {_describe(ex.filter)}", "model": ex.model,
                   "latency_s": ex.latency_s}
            args = ex.filter.to_filter_args(limit=self.limit)
            yield {"type": "action", "text": "Searching listings (structured filter)"}
            res = self.mcp.call_tool("filter_listings", args)
            header = f"[searched with filter_listings {json.dumps(args, ensure_ascii=False)}]\n"
            if res["is_error"]:
                self.stats["fallback_searches"] += 1
                yield {"type": "action", "text": "Structured search could not finish — retrying with Cubi's "
                                                 "free-text search (runs Cubi's own server-side language model)"}
                res = self.mcp.call_tool("search_properties", {"query": request, "lang": self.lang, "limit": self.limit})
                header = "[filter_listings failed; searched with search_properties (free text)]\n"
        else:
            if ex.filter is not None:
                self.filter = ex.filter
            self.stats["fallback_searches"] += 1
            yield {"type": "action", "text": "Request needs free-text search (no place, a whole country, or "
                                             "something like 'near the beach') — using Cubi's free-text search "
                                             "(runs Cubi's own server-side language model)"}
            res = self.mcp.call_tool("search_properties", {"query": request, "lang": self.lang, "limit": self.limit})
            header = "[searched with search_properties (free text)]\n"
        if not res["is_error"]:
            self.has_results = True
        yield header + res["text"]

    def _run_tool(self, name: str, args: dict) -> Iterator[dict | str]:
        if name == "search_homes":
            yield from self._search_homes(str(args.get("request", "")))
            return
        label = {"get_listing": "Opening the listing", "compare_asking_prices": "Comparing asking prices nearby",
                 "get_contact_options": "Looking up contact options"}.get(name, name)
        yield {"type": "action", "text": label}
        args.setdefault("lang", self.lang)
        yield self.mcp.call_tool(name, args)["text"]

    # ---- turn --------------------------------------------------------------
    def turn(self, text: str) -> Iterator[dict]:
        t0 = time.monotonic()
        self.lang = langmod.detect(text, default=self.lang)
        skill = self.skills[skillsmod.select(text, self.has_results)]
        tools = self._tools_for(skill)
        system = BASE_RULES.format(lang=self.lang) + "\n\n" + skill.body
        messages = [{"role": "system", "content": system}, *self.history, {"role": "user", "content": text}]
        turn_msgs: list[dict] = [{"role": "user", "content": text}]
        tool_text, used = "", set()
        extra = None if LOOP_THINKING else llm.NO_THINK

        answer = ""
        for step in range(MAX_STEPS + 1):
            force_answer = step == MAX_STEPS
            r = self.cli.chat.completions.create(
                model=llm.model(LOOP_ROLE), messages=messages, temperature=0.2, max_tokens=1500,
                tools=None if force_answer else tools, extra_body=extra,
            )
            if r.usage:
                self.stats["llm_in"] += r.usage.prompt_tokens or 0
                self.stats["llm_out"] += r.usage.completion_tokens or 0
            msg = r.choices[0].message
            if not msg.tool_calls:
                answer = msg.content or ""
                break
            call_msg = {"role": "assistant", "content": msg.content or "",
                        "tool_calls": [tc.model_dump(exclude_none=True) for tc in msg.tool_calls]}
            messages.append(call_msg)
            turn_msgs.append(call_msg)
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                used.add(tc.function.name)
                try:
                    result = ""
                    for ev in self._run_tool(tc.function.name, args):
                        if isinstance(ev, dict):
                            yield ev
                        else:
                            result = ev
                except MCPError as e:
                    result = f"error: {e}"
                    yield {"type": "action", "text": f"Tool error: {e}"}
                tool_text += result
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result[:TOOL_TEXT_CAP]})
                turn_msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result[:HISTORY_TOOL_CAP]})

        answer, report = guards.apply(answer, tool_text, self.lang, used)
        turn_msgs.append({"role": "assistant", "content": answer})
        self.history += turn_msgs
        yield {"type": "answer", "text": answer, "skill": skill.name, "lang": self.lang,
               "guards": report, "latency_s": round(time.monotonic() - t0, 2), "stats": dict(self.stats)}
