"""The agent: one conversation, a Nemotron tool loop, deterministic guards.

Per turn:
  1. language is detected in code; a skill is picked by keyword rule;
  2. Nemotron (the loop model) runs with that skill's SKILL.md as its system
     prompt and only that skill's tools, for at most MAX_STEPS tool calls;
  3. `search_homes` is local: a second Nemotron call extracts a structured filter
     (keeping the conversation's current filter for refinements) and code routes
     it to `filter_listings`, or to the connector's free-text search if no town
     or city was given;
  4. the answer passes URL, contact-detail and price-wording guards;
  5. the homes themselves are rendered by the app from the tool output
     (`listings` on the answer event), not written by the model — so a card
     can't be invented, and the model only writes a short summary.

`turn()` yields events — {"type": "action" | "answer", ...} — so the CLI and the
web server can show a short action log (never raw model reasoning).
"""
from __future__ import annotations

import json
import os
import time
from typing import Iterator

from . import extract as extractmod
from . import guards, lang as langmod, listings, llm, ordinals, skills as skillsmod, tavily_tool
from .fixtures import connect, listing_ref
from .mcp_client import CubiMCP, MCPError
from .schema import SearchFilter

MAX_STEPS = 5
LANG_NAMES = {"en": "English", "pt": "European Portuguese", "es": "Spanish", "fr": "French", "de": "German",
              "nl": "Dutch"}
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
    "Answer in the user's language ({lang}). Only describe homes the tools returned. Never invent "
    "URLs, ids, prices or contact details.\n"
    "In this app the skill's `filter_listings` and `search_properties` are both reached "
    "through `search_homes`, which chooses between them; call `search_homes` for any new "
    "or refined search, and `get_listing` for one home's details.\n"
    "After a search, the app shows every returned home as a numbered card under your reply, with "
    "price, place, size, bedrooms, features and the listing link, in the order returned. So do NOT "
    "list the homes and do not repeat their links (this replaces the skill's 'Present the results' "
    "rules). Write two or three sentences: what was searched, how many homes came back, and anything "
    "the user should know — a filter that was relaxed, homes that are older or pricier than the rest, "
    "or the best match by card number (\"#2\"). Limits are bounds: 'at least 1 bedroom' includes "
    "2-bedroom homes, so never call those mismatches. If nothing came back, say so and suggest one "
    "change to the search."
)


# Words for the one-line filter summary, per UI language. Types and features
# are the schema's canonical names; anything missing stays in English.
_WORDS = {
    "en": {"sale": "for sale", "rent": "to rent", "bed": "bed", "parking": "parking", "in": "in", "month": "/month"},
    "pt": {"sale": "venda", "rent": "arrendamento", "bed": "quartos", "parking": "estacionamento", "in": "em", "month": "/mês",
           "apartment": "apartamento", "house": "moradia", "villa": "moradia", "studio": "estúdio", "land": "terreno",
           "Pool": "piscina", "Terrace": "terraço", "Balcony": "varanda", "Garden": "jardim", "Elevator": "elevador",
           "Sea View": "vista mar"},
    "es": {"sale": "venta", "rent": "alquiler", "bed": "hab.", "parking": "garaje", "in": "en", "month": "/mes",
           "apartment": "piso", "house": "casa", "villa": "chalet", "studio": "estudio", "penthouse": "ático", "land": "terreno",
           "Pool": "piscina", "Terrace": "terraza", "Balcony": "balcón", "Garden": "jardín", "Elevator": "ascensor",
           "Sea View": "vistas al mar"},
    "fr": {"sale": "à vendre", "rent": "à louer", "bed": "ch.", "parking": "parking", "in": "à", "month": "/mois",
           "apartment": "appartement", "house": "maison", "land": "terrain", "Pool": "piscine", "Terrace": "terrasse",
           "Balcony": "balcon", "Garden": "jardin", "Elevator": "ascenseur", "Sea View": "vue mer"},
    "de": {"sale": "Kauf", "rent": "Miete", "bed": "Schlafzi.", "parking": "Stellplatz", "in": "in", "month": "/Monat",
           "apartment": "Wohnung", "house": "Haus", "land": "Grundstück", "Pool": "Pool", "Terrace": "Terrasse",
           "Balcony": "Balkon", "Garden": "Garten", "Elevator": "Aufzug", "Sea View": "Meerblick"},
    "nl": {"sale": "koop", "rent": "huur", "bed": "slpk", "parking": "parkeerplaats", "in": "in", "month": "/maand",
           "apartment": "appartement", "house": "huis", "land": "grond", "Pool": "zwembad", "Terrace": "terras",
           "Balcony": "balkon", "Garden": "tuin", "Elevator": "lift", "Sea View": "zeezicht"},
}


def _describe(f: SearchFilter, lang: str = "en") -> str:
    w = {**_WORDS["en"], **_WORDS.get(lang, {})}
    tr = lambda x: w.get(x, x)  # noqa: E731
    bits = [tr(f.transaction_type)]
    if f.type:
        bits.append("/".join(tr(t) for t in f.type))
    if f.min_bedrooms:
        bits.append(f"{f.min_bedrooms}+ {w['bed']}")
    month = w["month"] if f.transaction_type == "rent" else ""
    if f.min_price and f.max_price:
        bits.append(f"€{f.min_price:,.0f}–{f.max_price:,.0f}{month}")
    elif f.max_price:
        bits.append(f"≤ €{f.max_price:,.0f}{month}")
    elif f.min_price:
        bits.append(f"≥ €{f.min_price:,.0f}{month}")
    if f.features:
        bits.append(" + ".join(tr(x) for x in f.features))
    if f.has_parking:
        bits.append(w["parking"])
    if f.location:
        bits.append(f"{w['in']} " + ", ".join(f.location))
    return " · ".join(bits)


class Agent:
    def __init__(self, mcp: CubiMCP | None = None, cli=None, limit: int = 6):
        self.mcp = mcp or connect()
        self.cli = cli or llm.client()
        self.skills = skillsmod.load()
        self.limit = limit
        self.history: list[dict] = []
        self.filter: SearchFilter | None = None
        self.has_results = False
        self.lang = "en"
        self.stats = {"llm_in": 0, "llm_out": 0, "fallback_searches": 0, "filter_searches": 0}
        self.timings: list[tuple[str, float]] = []  # this turn's stages, seconds
        self.cards: list[dict] = []  # listings from this turn's last search, shown as cards
        self.shown: list[dict] = []  # the cards currently on screen (last search with results)
        self.seen_refs: set[str] = set()  # every listing id shown in this conversation
        self._message = ""
        self.focus: str | None = None  # the last home a price/contact/detail call was about
        self.sources: dict[str, dict] = {}  # this turn's area-research sources, S1.. → url

    # ---- tools -------------------------------------------------------------
    def _timed(self, stage: str, t0: float) -> None:
        self.timings.append((stage, round(time.monotonic() - t0, 2)))

    def _tools_for(self, skill: skillsmod.Skill) -> list[dict]:
        mcp_names = [t for t in skill.tools if t != "search_homes"]
        t0 = time.monotonic()
        tools = self.mcp.openai_tools(mcp_names) if mcp_names else []
        self._timed("mcp tools/list (cached after the first turn)", t0)
        if "search_homes" in skill.tools:
            tools.insert(0, SEARCH_HOMES_TOOL)
        if "research_area" in skill.tools:
            tools.append(tavily_tool.TOOL)
        return tools

    def _on_screen(self) -> str:
        if not self.shown:
            return ""
        rows = []
        for c in self.shown:
            place = ", ".join(listings.places(c.get("location", ""))[:2])
            rows.append(f"#{c['n']} {c.get('id', '?')} — {c.get('type', 'Home')}, {place}, {c.get('price_text', 'price n/a')}")
        return ("\n\nHomes on screen now (card number → listing id). When the user refers to a card, pass "
                "its listing id; the app also resolves card numbers itself:\n" + "\n".join(rows))

    def _resolve_listing(self, given: str) -> tuple[str | None, str]:
        """The listing a price/contact/detail call is about: the card the user named wins,
        then an id already shown, then the only card on screen. Returns (id, how)."""
        n = ordinals.ordinal(self._message, len(self.shown))
        if n and 1 <= n <= len(self.shown) and self.shown[n - 1].get("id"):
            return self.shown[n - 1]["id"], f"card #{n}"
        ref = listing_ref(given) if given else ""
        if ref and ref.lower() in self.seen_refs:
            return ref, "id from an earlier result"
        if self.focus:
            return self.focus, "the home discussed last"
        if len(self.shown) == 1 and self.shown[0].get("id"):
            return self.shown[0]["id"], "the only card on screen"
        return None, "unknown"

    def _search_homes(self, request: str) -> Iterator[dict | str]:
        ex = extractmod.extract(request, current=self.filter, cli=self.cli)
        self.timings.append((f"extract ({ex.model.split('/')[-1]}, {ex.attempts} attempt(s))", ex.latency_s))
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
            if not res["is_error"] and not listings.parse(res["text"]) and args.get("features"):
                # Features are hard filters on the connector, and tagging is uneven (a
                # studio with a lift is rarely tagged "Elevator"): relax once, say so.
                dropped = args.pop("features")
                self.stats["relaxed_searches"] = self.stats.get("relaxed_searches", 0) + 1
                yield {"type": "action", "text": "No exact matches — searching again without: " + ", ".join(dropped)}
                res = self.mcp.call_tool("filter_listings", args)
                header = (f"[no exact matches; searched again without the features {dropped} — say so to the "
                          f"user, these homes are not confirmed to have them] "
                          f"[filter_listings {json.dumps(args, ensure_ascii=False)}]\n")
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
            self.cards = listings.parse(res["text"])
            if self.cards:
                self.shown = self.cards
                self.focus = None  # a new result set: "it" no longer means the old home
                self.seen_refs |= {c["id"].lower() for c in self.cards if c.get("id")}
        yield header + res["text"]

    def _run_tool(self, name: str, args: dict) -> Iterator[dict | str]:
        if name == "search_homes":
            yield from self._search_homes(str(args.get("request", "")))
            return
        if name == "research_area":
            places, topics = list(args.get("places") or []), list(args.get("topics") or [])
            yield {"type": "action", "text": f"Researching {', '.join(places[:tavily_tool.MAX_PLACES])} on the web "
                                             f"(Tavily): {', '.join(topics) or 'quality of life'}"}
            try:
                text, st = tavily_tool.research_area(places, topics)
            except tavily_tool.TavilyError as e:
                yield {"type": "action", "text": f"Area research unavailable: {e}"}
                yield f"error: {e}. Tell the user area research is unavailable right now; do not answer from memory."
                return
            self.stats["tavily_searches"] = self.stats.get("tavily_searches", 0) + st["searches"]
            self.timings.append((f"tavily ({st['searches']} searches)", st["seconds"]))
            self.sources.update(st["sources"])
            yield (text + f"\n\nCite sources by their number, e.g. [S2], right after the claim — never write "
                   f"URLs. Write the whole answer in {LANG_NAMES.get(self.lang, 'English')}.")
            return
        label = {"get_listing": "Opening the listing", "compare_asking_prices": "Comparing asking prices nearby",
                 "get_contact_options": "Looking up contact options"}.get(name, name)
        if "listing_id" in args or name in ("get_listing", "compare_asking_prices", "get_contact_options"):
            ref, how = self._resolve_listing(str(args.get("listing_id") or ""))
            if ref is None:
                yield {"type": "action", "text": f"{label}: which home? (no card number or known id)"}
                yield ("error: the listing id is not one shown in this conversation. Ask the user which card "
                       "number they mean; do not guess an id.")
                return
            args["listing_id"] = ref
            self.focus = ref
            label += f" — {how} ({ref})"
        yield {"type": "action", "text": label}
        # The detected language of this turn, always: the model copies an earlier
        # turn's lang from history (an English question got a Dutch contact reply).
        args["lang"] = self.lang
        yield self.mcp.call_tool(name, args)["text"]

    # ---- turn --------------------------------------------------------------
    def turn(self, text: str) -> Iterator[dict]:
        t0 = time.monotonic()
        self.timings = []
        self.cards = []
        self._message = text
        self.sources = {}
        calls0 = len(self.mcp.calls)
        self.lang = langmod.detect(text, default=self.lang)
        skill = self.skills[skillsmod.select(text, self.has_results)]
        tools = self._tools_for(skill)
        system = BASE_RULES.format(lang=self.lang) + "\n\n" + skill.body + self._on_screen()
        messages = [{"role": "system", "content": system}, *self.history, {"role": "user", "content": text}]
        turn_msgs: list[dict] = [{"role": "user", "content": text}]
        tool_text, used = "", set()
        extra = None if LOOP_THINKING else llm.NO_THINK

        def run_call(name: str, args: dict, call_id: str) -> Iterator[dict]:
            nonlocal tool_text
            used.add(name)
            try:
                result = ""
                for ev in self._run_tool(name, args):
                    if isinstance(ev, dict):
                        yield ev
                    else:
                        result = ev
            except MCPError as e:
                result = f"error: {e}"
                yield {"type": "action", "text": f"Tool error: {e}"}
            tool_text += result
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result[:TOOL_TEXT_CAP]})
            turn_msgs.append({"role": "tool", "tool_call_id": call_id, "content": result[:HISTORY_TOOL_CAP]})

        # A find-homes turn that doesn't point at a card on screen is a search: run it
        # in code. Saves a round trip, and the model can't answer "from memory" with no
        # cards — it did, when a search was repeated word for word.
        if skill.name == "find-homes" and ordinals.ordinal(text, len(self.shown)) is None:
            call = {"id": "auto_search", "type": "function",
                    "function": {"name": "search_homes", "arguments": json.dumps({"request": text}, ensure_ascii=False)}}
            call_msg = {"role": "assistant", "content": "", "tool_calls": [call]}
            messages.append(call_msg)
            turn_msgs.append(call_msg)
            yield from run_call("search_homes", {"request": text}, "auto_search")
            tools = [t for t in tools if t["function"]["name"] != "search_homes"]

        answer = ""
        for step in range(MAX_STEPS + 1):
            force_answer = step == MAX_STEPS
            t_llm = time.monotonic()
            r = self.cli.chat.completions.create(
                model=llm.model(LOOP_ROLE), messages=messages, temperature=0.2, max_tokens=1500,
                tools=None if force_answer or not tools else tools, extra_body=extra,
            )
            out_tok = (r.usage.completion_tokens or 0) if r.usage else 0
            self._timed(f"loop step {step} ({llm.model(LOOP_ROLE).split('/')[-1]}, {out_tok} tokens out)", t_llm)
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
                yield from run_call(tc.function.name, args, tc.id)

        for c in self.mcp.calls[calls0:]:
            self.timings.append((f"mcp {c['tool']}" + (" (error)" if c["is_error"] else ""), c["seconds"]))
        cited = 0
        if "research_area" in used:
            answer, cited = tavily_tool.link_citations(answer, self.sources, self.lang)
            tool_text += "\n".join(src["url"] for src in self.sources.values())
        answer, report = guards.apply(answer, tool_text, self.lang, used)
        report["citations_linked"] = cited
        turn_msgs.append({"role": "assistant", "content": answer})
        self.history += turn_msgs
        yield {"type": "answer", "text": answer, "skill": skill.name, "lang": self.lang,
               "guards": report, "latency_s": round(time.monotonic() - t0, 2), "stats": dict(self.stats),
               "timings": list(self.timings), "listings": list(self.cards)}
