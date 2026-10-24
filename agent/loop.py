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
import re
import time
from typing import Generator, Iterator

import httpx

from . import extract as extractmod
from . import guards, inventory, lang as langmod, listings, llm, ordinals, pivot, similar as similarmod, steps, skills as skillsmod, suggest, tavily_tool, x_tool
from .fixtures import connect, listing_ref
from .mcp_client import CubiMCP, MCPError
from .schema import SearchFilter

MAX_STEPS = 5
CITE_AGAIN = ("Rewrite that answer with the same content, putting the number of the source each point comes "
              "from right after it, like [S2]. Drop any point no source supports. Answer in {lang}.")
MAX_SEARCH_PLACES = 3  # a multi-place search runs once per place, up to this many
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
    "2-bedroom homes, so never call those mismatches. Wishes such as a pool, a sea view, a lift or "
    "'by the sea' rank the results rather than filter them: say a home has one only if the tool "
    "result lists it for that home, and never say that all the homes have it. Take any price range "
    "from every returned home, not the first few. If nothing came back, say so and suggest one "
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
    # Russian is pivoted through English (agent/pivot.py); only this line is written natively.
    "ru": {"sale": "продажа", "rent": "аренда", "bed": "спальни", "parking": "парковка", "in": "в", "month": "/мес.",
           "apartment": "квартира", "house": "дом", "villa": "вилла", "studio": "студия", "land": "участок",
           "Pool": "бассейн", "Terrace": "терраса", "Balcony": "балкон", "Garden": "сад", "Elevator": "лифт",
           "Sea View": "вид на море"},
}


def _describe(f: SearchFilter, lang: str = "en") -> str:
    w = {**_WORDS["en"], **_WORDS.get(lang, {})}
    tr = lambda x: w.get(x, x)  # noqa: E731
    bits = [tr(f.transaction_type)]
    if f.type:
        bits.append("/".join(tr(t) for t in f.type))
    if f.min_bedrooms and f.max_bedrooms == f.min_bedrooms:
        bits.append(f"{f.min_bedrooms} {w['bed']}")
    elif f.min_bedrooms:
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


def _long_date(iso: str | None) -> str:
    """'2026-05-02' -> '2 May 2026': one unambiguous form for the model to copy."""
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _chip_key(text: str) -> str:
    """Button text as compared to recognise a translated button (any script)."""
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


class Agent:
    def __init__(self, mcp: CubiMCP | None = None, cli=None, limit: int = 6):
        self.mcp = mcp or connect()
        self.cli = cli or llm.client()
        self.skills = skillsmod.load()
        self.limit = limit
        self.history: list[dict] = []
        self.filter: SearchFilter | None = None
        self.has_results = False
        self.lang = "en"  # the language this turn runs in: one of the six (English when pivoted)
        self.user_lang = "en"  # the language the user writes in: any (agent/pivot.py)
        self.user_lang_name = "English"
        self.data_lang = "en"  # the language asked of Cubi's connector
        self._chips: dict[str, str] = {}  # a translated button → its English original
        self.sale_only: list[str] = []
        self.stats = {"llm_in": 0, "llm_out": 0, "fallback_searches": 0, "filter_searches": 0}
        self.timings: list[tuple[str, float]] = []  # this turn's stages, seconds
        self.cards: list[dict] = []  # listings from this turn's last search, shown as cards
        self.shown: list[dict] = []  # the cards currently on screen (last search with results)
        self.seen_refs: set[str] = set()  # every listing id shown in this conversation
        self._message = ""
        self.focus: str | None = None  # the last home a price/contact/detail call was about
        self.sources: dict[str, dict] = {}  # this turn's area-research sources, S1.. → url
        self.last_skill: str | None = None
        self.inventory: dict | None = None  # last budget comparison: {"args", "result"}
        self.bars: dict | None = None  # this turn's budget bars, for the page
        self.similar: dict | None = None  # this turn's side-by-side table, for the page
        self.area_places: list[str] = []  # places of the last area research, for suggestions
        self._pair: tuple[int, int] | None = None  # card numbers of a pair comparison in flight
        self.done: set[str] = set()  # what this conversation asked and did, so suggestions don't repeat it
        self.price_history: dict | None = None  # this turn's price timeline, for the page
        self.x_url: str | None = None  # this turn's link to X's live search for the home's city
        self.x_posts: list[dict] = []  # this turn's posts from X, when X_BEARER_TOKEN is set

    # ---- tools -------------------------------------------------------------
    def _timed(self, stage: str, t0: float) -> None:
        self.timings.append((stage, round(time.monotonic() - t0, 2)))

    def _tools_for(self, skill: skillsmod.Skill) -> list[dict]:
        # search_homes and the budget comparison run in code, not as model tools.
        mcp_names = [t for t in skill.tools if t not in ("search_homes", inventory.TOOL)]
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

    def _filter_call(self, args: dict) -> Generator[dict, None, tuple[dict, str]]:
        """filter_listings, relaxed once without features when nothing matches."""
        res = self.mcp.call_tool("filter_listings", args)
        header = f"[searched with filter_listings {json.dumps(args, ensure_ascii=False)}]\n"
        if not res["is_error"] and not listings.parse(res["text"]) and args.get("features"):
            # Features are hard filters on the connector, and tagging is uneven (a
            # studio with a lift is rarely tagged "Elevator"): relax once, say so.
            args = dict(args)
            dropped = args.pop("features")
            self.stats["relaxed_searches"] = self.stats.get("relaxed_searches", 0) + 1
            yield {"type": "action", "text": "No exact matches — searching again without: " + ", ".join(dropped)}
            res = self.mcp.call_tool("filter_listings", args)
            header = (f"[no exact matches; searched again without the features {dropped} — say so to the "
                      f"user, these homes are not confirmed to have them] "
                      f"[filter_listings {json.dumps(args, ensure_ascii=False)}]\n")
        if not res["is_error"] and not listings.parse(res["text"]):
            header += self._why_none(args)
        return res, header

    def _any(self, args: dict) -> bool:
        res = self.mcp.call_tool("filter_listings", {**args, "limit": 1})
        return not res["is_error"] and bool(listings.parse(res["text"]))

    def _why_none(self, args: dict) -> str:
        """Why a search found nothing, measured with up to two one-row probes. "Lyon
        flats to rent under €1,200" found none and the model advised a bigger budget
        or nearby towns — Cubi had no Lyon rentals at any price (live 2026-10-22)."""
        where = ", ".join(args.get("location") or []) or "this area"
        priced = {k: v for k, v in args.items() if k not in ("min_price", "max_price")}
        if priced != args:
            self.stats["zero_probes"] = self.stats.get("zero_probes", 0) + 1
            if self._any(priced):
                return ("[why none: the same search without the price limit does find homes, so the "
                        "budget is what rules them out — say so]\n")
        if args.get("transaction_type") == "rent":
            sale = {k: v for k, v in priced.items() if k not in ("transaction_type", "price_period")}
            self.stats["zero_probes"] = self.stats.get("zero_probes", 0) + 1
            if self._any(sale):
                self.sale_only += list(args.get("location") or [])
                return (f"[why none: Cubi lists no homes like this to rent in {where} at any price, though it "
                        f"has homes for sale there. Say this, in the user's language, and add nothing else — "
                        f"no other budget, town or search to try: \"Cubi has no listings like this to rent in "
                        f"{where} yet: its rental listings don't cover {where}, so a higher rent would not "
                        f"help. It does list homes for sale there.\"]\n")
        if priced != args:
            return (f"[why none: Cubi has no homes like this in {where} at any price. Say so; do not "
                    f"suggest a higher budget]\n")
        return ""

    def _filter_per_place(self, args: dict, places: list[str]) -> Generator[dict, None, tuple[dict, str]]:
        """One filter_listings call per place, cards grouped by place and renumbered."""
        per = max(2, -(-self.limit // len(places)))
        merged: list[dict] = []
        notes, failed = [], []
        for place in places:
            yield {"type": "action", "text": f"Searching listings in {place} (structured filter)"}
            res, header = yield from self._filter_call({**args, "location": [place], "limit": per})
            if res["is_error"]:
                failed.append(place)
                notes.append(f"{place}: the search failed")
                continue
            cards = listings.parse(res["text"])
            notes.append(f"{place}: {len(cards)} shown" + ("" if cards else " (no matches)")
                         + (" — " + header.strip() if "no exact matches" in header or "[why none" in header else ""))
            merged.extend(cards)
        if failed and len(failed) == len(places):
            return res, ""
        for i, c in enumerate(merged, 1):
            c["n"] = i
        head = (f"[searched with filter_listings once per place {json.dumps({**args, 'limit': per}, ensure_ascii=False)}]\n"
                f"Per place: " + "; ".join(notes) + ". Cards are grouped by place. Report each place's "
                "result as given here; a place with no matches had none under these filters.")
        return {"is_error": False, "text": listings.render_cards(head, merged)}, ""

    def _search_homes(self, request: str) -> Iterator[dict | str]:
        offered = [p for p in self.sale_only if suggest.norm(suggest.for_sale(self.lang, p)) == suggest.norm(request)]
        self.sale_only = []   # places _why_none found with homes for sale but none to rent
        if offered and self.filter is not None:
            # The "homes for sale in Lyon" button: the extractor kept "to rent" from
            # the search before it (live 2026-10-22), so the switch is made here.
            f = self.filter.model_copy(update={"transaction_type": "sale", "min_price": None, "max_price": None})
            ex = extractmod.Extraction(f, extractmod.route_for(f), "button", 0.0, 0, {})
        else:
            ex = extractmod.extract(request, current=self.filter, cli=self.cli)
        self.timings.append((f"extract ({ex.model.split('/')[-1]}, {ex.attempts} attempt(s))", ex.latency_s))
        self.stats["llm_in"] += ex.usage.get("in", 0)
        self.stats["llm_out"] += ex.usage.get("out", 0)
        if ex.filter is not None and ex.route == "filter":
            self.filter = ex.filter
            self.stats["filter_searches"] += 1
            yield {"type": "action", "text": f"Understood: {_describe(ex.filter, self.user_lang)}", "model": ex.model,
                   "latency_s": ex.latency_s}
            args = ex.filter.to_filter_args(limit=self.limit)
            args["lang"] = self.data_lang
            places = list(args.get("location") or [])
            if len(places) > 1:
                # One search per place: a single multi-place filter returns whichever
                # place sorts first (Porto + Valencia came back all Valencia), and the
                # model then said Porto had nothing.
                res, header = yield from self._filter_per_place(args, places[:MAX_SEARCH_PLACES])
            else:
                yield {"type": "action", "text": "Searching listings (structured filter)"}
                res, header = yield from self._filter_call(args)
            if res["is_error"]:
                self.stats["fallback_searches"] += 1
                yield {"type": "action", "text": "Structured search could not finish — retrying with Cubi's "
                                                 "free-text search (runs Cubi's own server-side language model)"}
                res = self.mcp.call_tool("search_properties", {"query": request, "lang": self.data_lang, "limit": self.limit})
                header = "[filter_listings failed; searched with search_properties (free text)]\n"
        else:
            if ex.filter is not None:
                self.filter = ex.filter
            self.stats["fallback_searches"] += 1
            yield {"type": "action", "text": "Request needs free-text search (no place, a whole country, or "
                                             "something like 'near the beach') — using Cubi's free-text search "
                                             "(runs Cubi's own server-side language model)"}
            res = self.mcp.call_tool("search_properties", {"query": request, "lang": self.data_lang, "limit": self.limit})
            header = "[searched with search_properties (free text)]\n"
        if not res["is_error"]:
            self.has_results = True
            self.cards = listings.parse(res["text"])
            if self.cards:
                self.shown = self.cards
                self.focus = None  # a new result set: "it" no longer means the old home
                self.seen_refs |= {c["id"].lower() for c in self.cards if c.get("id")}
        yield header + res["text"]

    def _compare_budget(self, request: str) -> Iterator[dict | str]:
        """compare_inventory for the cities and budget in the request. A refinement
        ("and up to 500k?") keeps the cities and cohort; only the budget changes."""
        ex = extractmod.extract(request, current=self.filter, cli=self.cli)
        self.timings.append((f"extract ({ex.model.split('/')[-1]}, {ex.attempts} attempt(s))", ex.latency_s))
        self.stats["llm_in"] += ex.usage.get("in", 0)
        self.stats["llm_out"] += ex.usage.get("out", 0)
        f, prev = ex.filter, self.inventory
        if f is None:
            yield "error: the request could not be read. Ask the user to name the cities and the budget."
            return
        places = list(f.location)
        if len(places) < 2 and prev:
            places = list(prev["args"]["places"])
        if len(places) < 2:
            yield {"type": "action", "text": "A budget comparison needs two or three cities"}
            yield "error: fewer than two cities were named. Ask which two or three cities to compare."
            return
        if not f.max_price:
            yield {"type": "action", "text": "A budget comparison needs a budget"}
            yield "error: no budget was given. Ask the user for their budget (an asking-price cap)."
            return
        # The budget is a cap; a floor the extractor read from the same number
        # ("400k" → 400k–400k) would show on screen though nothing counts it.
        f = f.model_copy(update={"location": places[:inventory.MAX_PLACES], "transaction_type": "sale",
                                 "min_price": None})
        self.filter = f
        args = inventory.args_for(f, places)
        yield {"type": "action", "text": f"Understood: {_describe(f.model_copy(update={'has_parking': None}), self.user_lang)}",
               "model": ex.model, "latency_s": ex.latency_s}
        yield {"type": "action", "text": f"Counting listings within budget in {', '.join(args['places'])} "
                                         f"(Cubi compare_inventory)"}
        res = self.mcp.call_tool(inventory.TOOL, args)
        result = None
        if not res["is_error"]:
            try:
                result = json.loads(res["text"])
            except json.JSONDecodeError:
                result = None
        if not result or not result.get("ok"):
            yield {"type": "action", "text": "Budget comparison: not available right now"}
            yield ("error: the comparison could not be run right now. Tell the user and offer to try again; "
                   "do not estimate any figure.")
            return
        same_cohort = prev and inventory.cohort_key(prev["args"]) == inventory.cohort_key(args)
        previous = prev["result"] if same_cohort and prev["args"]["max_price"] != args["max_price"] else None
        cards = inventory.to_cards(result)
        self.cards = cards
        if cards:
            self.shown = cards
            self.focus = None
            self.seen_refs |= {c["id"].lower() for c in cards if c.get("id")}
        self.has_results = True
        self.bars = inventory.bars(result, previous)
        self.inventory = {"args": args, "result": result}
        text = inventory.tool_text(result, previous, cards)
        yield text + ("\n" + inventory.PARKING_NOTE if f.has_parking else "")

    def _run_tool(self, name: str, args: dict) -> Iterator[dict | str]:
        if name == "search_homes":
            yield from self._search_homes(str(args.get("request", "")))
            return
        if name == inventory.TOOL:
            yield from self._compare_budget(str(args.get("request", "")))
            return
        if name == "home_news":
            yield from self._home_news()
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
            self.area_places = [p.split(",")[0].strip() for p in places[:tavily_tool.MAX_PLACES]]
            yield (text + "\n\nCite sources by their number, e.g. [S2], right after the claim — never write URLs.")
            return
        label = {"get_listing": "Opening the listing", "compare_asking_prices": "Comparing asking prices nearby",
                 "get_contact_options": "Looking up contact options",
                 similarmod.TOOL: (f"Comparing two homes feature by feature" if args.get("compare_with")
                                   else f"Finding homes like it in {args.get('city') or '?'}")}.get(name, name)
        how = ""
        if "listing_id" in args or name in ("get_listing", "compare_asking_prices", "get_contact_options", similarmod.TOOL):
            ref, how = self._resolve_listing(str(args.get("listing_id") or ""))
            if ref is None:
                yield {"type": "action", "text": f"{label}: which home? (no card number or known id)"}
                yield ("error: the listing id is not one shown in this conversation. Ask the user which card "
                       "number they mean; do not guess an id.")
                return
            args["listing_id"] = ref
            self.focus = ref
            label += f" — {how} ({ref})"
            done_kind = {"compare_asking_prices": "price", "get_contact_options": "contact"}.get(name)
            if done_kind:
                self.done.add(suggest.key(done_kind, ref))
        else:
            how = ""
        yield {"type": "action", "text": label}
        # The detected language of this turn, always: the model copies an earlier
        # turn's lang from history (an English question got a Dutch contact reply).
        args["lang"] = self.data_lang
        res = self.mcp.call_tool(name, args)
        if res["is_error"]:
            # Said plainly, or the model explains the failure itself ("probably too few
            # comparables") — a reason nobody measured.
            yield {"type": "action", "text": f"{label}: not available right now"}
            yield (f"error: the {name} call failed ({res['text'][:200].strip()}). Tell the user this could "
                   f"not be checked right now and offer to try again; do not guess a reason or a result.")
            return
        if name == similarmod.TOOL:
            yield from self._similar_result(res["text"], how)
            return
        if name == "compare_asking_prices":
            yield self._no_band_brief(res["text"], how)
            return
        yield res["text"]

    @staticmethod
    def _no_band_brief(text: str, how: str) -> str:
        """No range: one ready sentence with the measured reason. Left to itself the
        model turned "no band" into a verdict ("Der Preis von #1 liegt nicht im
        Vergleichsrahmen", live 2026-10-22) or a paragraph of method."""
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return text
        if not isinstance(body, dict):
            return text
        if body.get("band"):
            n = body.get("n_comps") or 0
            how_many = ("Do not call the comparison thin or the comparables few."
                        if n >= guards.AMPLE_COMPS else "You may say the comparison rests on few homes.")
            return text + f"\n\n[{n} comparable homes] {how_many}"
        n_card = ordinals.ordinal(how, 99) if how.startswith("card") else None
        label = f"#{n_card}" if n_card else "this home"
        n, city = body.get("n_comps"), body.get("city") or "the same city"
        if body.get("reason") == "comparables_disagree" and n:
            why = (f"the {n} comparable homes Cubi has in {city} vary too much in asking price "
                   f"to give a fair range")
        elif n:
            why = f"Cubi has only {n} comparable {'home' if n == 1 else 'homes'} in {city}, too few for a range"
        else:
            why = f"Cubi has no comparable homes in {city} with an asking price"
        return (text + f"\n\n[no range for {label}] Say this, in the user's language, and nothing more about "
                f"the price: \"There is no range of asking prices to compare {label} with: {why}. That says "
                f"nothing about whether its price is high or low.\" Then one short line that this compares "
                f"asking prices, not a valuation. Never say the price is outside, below, above or in line "
                f"with anything.")

    def _home_news(self) -> Iterator[dict | str]:
        """The home's observed price changes (Cubi) and recent news about its city
        (Tavily, cited). X is linked, not read: no search API without a paid key."""
        ref, how = self._resolve_listing("")
        if ref is None:
            yield {"type": "action", "text": "Price history: which home? (no card number or known id)"}
            yield "error: no home is on screen or named. Ask the user which card number they mean."
            return
        self.focus = ref
        self.done.add(suggest.key("news", ref))
        n = ordinals.ordinal(how, 99) if how.startswith("card") else None
        label = f"#{n}" if n else "this home"
        yield {"type": "action", "text": f"Checking the price history — {how} ({ref})"}
        hist = None
        try:
            res = self.mcp.call_tool("get_price_history", {"listing_id": ref})
            hist = None if res["is_error"] else json.loads(res["text"])
        except (MCPError, json.JSONDecodeError):
            hist = None
        lines = []
        if not hist:
            yield {"type": "action", "text": "Price history: not available right now"}
            lines.append("[price history] Not available right now: say so; do not guess any price change.")
        else:
            # Changes are observable from the later of the log's start and the day Cubi
            # first saw the listing: "tracked since May 2" for a listing seen yesterday
            # was false (live 2026-10-22).
            watched = max(d for d in (hist.get("tracked_since"), hist.get("on_cubi_since")) if d) \
                if (hist.get("tracked_since") or hist.get("on_cubi_since")) else None
            hist = {**hist, "tracked_since": watched}
            self.price_history = {**{k: hist.get(k) for k in ("current_price", "currency", "on_cubi_since",
                                                               "tracked_since", "changes", "total_change_pct",
                                                               "first_observed_price", "city")}, "card": n}
            # One date, said one way. Given the log's start AND the first-seen date,
            # the model wrote "first appeared on 2026-05-02 (initial sighting
            # 2025-08-26)" (live 2026-10-22). So: only the date changes became
            # visible from, and why, in a sentence to use as written.
            why = ("when the listing first appeared on Cubi" if watched == hist.get("on_cubi_since")
                   else "when Cubi's price log began")
            when = _long_date(watched)
            lines.append(f"[price history for {label}] Current asking price €{hist.get('current_price') or 0:,.0f}.")
            if not hist.get("changes"):
                lines.append(f"Say this, in the user's language: \"Cubi has seen no change in this home's asking "
                             f"price since {when}, {why}.\" Do not mention any other date for the price.")
            else:
                lines.append(f"Observed changes since {when}, {why} (state each with its date):")
                for c in hist.get("changes") or []:
                    lines.append(f"- {_long_date(c['date'])}: €{c['old_price']:,.0f} → €{c['new_price']:,.0f} "
                                 f"({c['pct']:+.1f}%)")
                if hist.get("total_change_pct") is not None and len(hist["changes"]) > 1:
                    lines.append(f"In total: {hist['total_change_pct']:+.1f}% (from €{hist['first_observed_price']:,.0f}).")
        # The place the user sees on the card (and that the suggestion named) wins
        # over the listing's stored city: live 2026-10-22 a card shown in "Lisboa"
        # was stored as Cascais, and the news search went to the wrong town.
        card = next((c for c in self.shown if c.get("id") == ref), {})
        searched = list(self.filter.location) if self.filter and self.filter.location else []
        city = suggest.news_place(card, searched) or (hist or {}).get("city") or ""
        country = (hist or {}).get("country") or ""
        if city:
            place = f"{city}, {country}" if country else city
            yield {"type": "action", "text": f"Searching recent news about {city} (Tavily, last {tavily_tool.NEWS_DAYS} days)"}
            try:
                text, st = tavily_tool.latest_news(place, first_id=len(self.sources) + 1)
                self.sources.update(st["sources"])
                self.stats["tavily_searches"] = self.stats.get("tavily_searches", 0) + st["searches"]
                self.timings.append((f"tavily news ({st['searches']} searches)", st["seconds"]))
                lines.append("\n" + text + "\n\nCite news by its number, e.g. [S2], right after the point. "
                             "Never write URLs.")
            except tavily_tool.TavilyError as e:
                yield {"type": "action", "text": f"News search unavailable: {e}"}
                lines.append("[news] Unavailable right now: say so; do not answer from memory.")
            self.x_url = tavily_tool.x_search_url(city)
            x_text = None
            if x_tool.enabled():
                yield {"type": "action", "text": f"Reading recent posts about housing in {city} on X (last 7 days)"}
                try:
                    first = 1 + sum(1 for k in self.sources if k.startswith("X"))
                    x_text, st = x_tool.recent_posts(city, first_id=first)
                    self.sources.update(st["sources"])
                    self.x_posts = st["posts"]
                    self.stats["x_posts_read"] = self.stats.get("x_posts_read", 0) + st["returned"]
                    self.timings.append(("x recent search", st["seconds"]))
                except (x_tool.XError, httpx.HTTPError) as e:
                    yield {"type": "action", "text": f"Posts on X unavailable: {e}"}
            if x_text:
                lines.append("\n" + x_text)
            else:
                lines.append("The app also shows a link to the latest posts about the city on X; you have not "
                             "read them, so don't describe them.")
        yield "\n".join(lines)

    def _two_cards(self, text: str) -> list[dict]:
        """The two cards a message names by number ("#1 and #4"), when both are on screen."""
        import re
        nums = [int(x) for x in re.findall(r"(?:#|\bn[º°o]\.?\s*)(\d{1,2})\b", text.lower())]
        cards = [next((c for c in self.shown if c.get("n") == n and c.get("id")), None) for n in nums[:2]]
        return cards if len(cards) == 2 and all(cards) and cards[0] is not cards[1] else []

    def _similar_result(self, text: str, how: str) -> Iterator[dict | str]:
        """The side-by-side table from find_similar_elsewhere; its matches become the cards."""
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {}
        if result.get("error") == "same_city":
            yield "error: the home is already in that city. Offer its price check instead, or another city."
            return
        if not result.get("ok") or not result.get("seed"):
            yield {"type": "action", "text": "Similar homes: not available right now"}
            yield ("error: the comparison could not be run right now. Tell the user and offer to try again; "
                   "do not guess any figure.")
            return
        pair, self._pair = self._pair, None
        seed_id = (result.get("seed") or {}).get("id")
        if result.get("mode") == "pair":
            ids = sorted(str(x) for x in [seed_id] + [m.get("id") for m in result.get("matches") or []])
            self.done.add(suggest.key("pair", "+".join(ids)))
        elif result.get("city"):
            self.done.add(suggest.key("similar", seed_id, suggest.english_city(result["city"])))
        if result.get("mode") == "pair" and pair:
            # Both homes are already cards on screen: keep them, and their numbers.
            self.similar = similarmod.table(result, seed_card=pair[0], match_cards=[pair[1]])
            yield {"type": "action", "text": f"Comparing #{pair[0]} and #{pair[1]} feature by feature"}
            yield similarmod.tool_text(result, [], f"#{pair[0]}", match_labels=[f"#{pair[1]}"])
            return
        seed_n = ordinals.ordinal(how, 99) if how.startswith("card") else None
        cards = similarmod.to_cards(result)
        self.similar = similarmod.table(result, seed_card=seed_n)
        self.cards = cards
        if cards:
            self.shown = cards
            self.seen_refs |= {c["id"].lower() for c in cards if c.get("id")}
        yield {"type": "action", "text": f"{len(cards)} matching home(s) in {result.get('city')}, matched on "
                                         f"features and surroundings, not price"}
        yield similarmod.tool_text(result, cards, f"#{seed_n}" if seed_n else "the home asked about")

    # ---- turn --------------------------------------------------------------
    def turn(self, text: str) -> Iterator[dict]:
        """One user message in any language. The six run natively; any other is
        translated to English, run, and the answer translated back (agent/pivot.py)."""
        key = _chip_key(text)
        if key in self._chips and not pivot.native(self.user_lang):
            # A translated button: run its English original, no translation call.
            yield from self._pivoted(self._chips[key], time.monotonic(), [])
            return
        pre: list[tuple[str, float]] = []
        found = None
        if langmod.needs_check(text):
            t0 = time.monotonic()
            found = pivot.identify(self.cli, text)
            pre.append(("identify language", round(time.monotonic() - t0, 2)))
        if found and not pivot.native(found[0]):
            self.user_lang, self.user_lang_name, english = found
            steps.warm(self.cli, self.user_lang, self.user_lang_name)  # no-op once warmed
            self.stats["pivot_turns"] = self.stats.get("pivot_turns", 0) + 1
            yield from self._pivoted(english, time.monotonic() - pre[0][1], pre)
            return
        if not found and not pivot.native(self.user_lang) and not langmod.detect(text, default=""):
            # "#2?", "Kraków": nothing says the language changed, so the conversation stays in it.
            yield from self._pivoted(text, time.monotonic(), pre)
            return
        lang = found[0] if found else langmod.detect(text, default=self.lang)
        self.user_lang, self.user_lang_name, self.data_lang = lang, LANG_NAMES[lang], lang
        for ev in self._turn(text, lang):
            if ev.get("type") == "answer" and pre:
                ev["timings"] = pre + ev["timings"]
            yield self._local_step(ev)

    def _local_step(self, ev: dict) -> dict:
        """A step-log line in the user's language (agent/steps.py)."""
        if ev.get("type") == "action" and self.user_lang != "en":
            ev = {**ev, "text": steps.localize(ev.get("text", ""), self.user_lang)}
        return ev

    def _pivoted(self, english: str, t0: float, pre: list[tuple[str, float]]) -> Iterator[dict]:
        self.data_lang = self.user_lang if self.user_lang in pivot.CUBI_I18N else "en"
        for ev in self._turn(english, "en"):
            if ev.get("type") != "answer":
                yield self._local_step(ev)
                continue
            t1 = time.monotonic()
            out = pivot.back(self.cli, self.user_lang_name, ev["text"], ev["suggestions"], self.user_lang)
            timings = [*pre, *ev["timings"], ("translate back", round(time.monotonic() - t1, 2))]
            if out:
                ev["text"], chips = out
                self._chips.update({_chip_key(c): s for c, s in zip(chips, ev["suggestions"])})
                ev["suggestions"] = chips
            else:
                ev["text"] += "\n\n" + pivot.NOTE
                self.stats["pivot_failures"] = self.stats.get("pivot_failures", 0) + 1
            ev.update(lang=self.user_lang, via="en", timings=timings, latency_s=round(time.monotonic() - t0, 2),
                      stats=dict(self.stats))
            yield ev

    def _turn(self, text: str, lang: str) -> Iterator[dict]:
        t0 = time.monotonic()
        self.timings = []
        self.cards = []
        self._message = text
        self.sources = {}
        self.bars = None
        self.similar = None
        self.price_history = None
        self.x_url = None
        self.x_posts = []
        calls0 = len(self.mcp.calls)
        self.lang = lang
        skill = self.skills[skillsmod.select(text, self.has_results, self.last_skill)]
        self.last_skill = skill.name
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
            # Named at the end of every tool result, where the model looks last: a
            # system-prompt rule alone lost to history (an English question after
            # Dutch turns was answered in Dutch, live 2026-10-20).
            lang_note = f"\n\n[Answer in {LANG_NAMES.get(self.lang, 'English')}.]"
            messages.append({"role": "tool", "tool_call_id": call_id,
                             "content": result[:TOOL_TEXT_CAP] + lang_note})
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
        elif skill.name == "similar-elsewhere" and len(self._two_cards(text)) == 2:
            # "Compare #1 and #4 feature by feature": both cards are on screen,
            # so code resolves them and asks for the pair — no search, no guess.
            a, b = self._two_cards(text)
            args = {"listing_id": a["id"], "compare_with": b["id"]}
            call = {"id": "auto_pair", "type": "function",
                    "function": {"name": similarmod.TOOL, "arguments": json.dumps(args)}}
            call_msg = {"role": "assistant", "content": "", "tool_calls": [call]}
            messages.append(call_msg)
            turn_msgs.append(call_msg)
            self._pair = (a["n"], b["n"])
            yield from run_call(similarmod.TOOL, args, "auto_pair")
            tools = []
        elif skill.name == "home-news":
            call = {"id": "auto_news", "type": "function", "function": {"name": "home_news", "arguments": "{}"}}
            call_msg = {"role": "assistant", "content": "", "tool_calls": [call]}
            messages.append(call_msg)
            turn_msgs.append(call_msg)
            yield from run_call("home_news", {}, "auto_news")
            tools = []
        elif skill.name == "compare-budget":
            # Same reason: the figures come from one call made in code, and the
            # model only writes around them.
            call = {"id": "auto_budget", "type": "function",
                    "function": {"name": inventory.TOOL, "arguments": json.dumps({"request": text}, ensure_ascii=False)}}
            call_msg = {"role": "assistant", "content": "", "tool_calls": [call]}
            messages.append(call_msg)
            turn_msgs.append(call_msg)
            yield from run_call(inventory.TOOL, {"request": text}, "auto_budget")
            tools = []

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
        if self.sources and answer and not tavily_tool.CITATION.search(tavily_tool.normalise_citations(answer)):
            # Uncited area answers happen: ask once more
            # with the rule restated, and keep the first answer if the retry fails too.
            t_llm = time.monotonic()
            r = self.cli.chat.completions.create(
                model=llm.model(LOOP_ROLE), temperature=0.2, max_tokens=1500, extra_body=extra,
                messages=[*messages, {"role": "assistant", "content": answer},
                          {"role": "user", "content": CITE_AGAIN.format(lang=LANG_NAMES.get(self.lang, "English"))}],
            )
            self._timed("citation retry", t_llm)
            retry = r.choices[0].message.content or ""
            self.stats["citation_retries"] = self.stats.get("citation_retries", 0) + 1
            if tavily_tool.CITATION.search(tavily_tool.normalise_citations(retry)):
                answer = retry
        cited = 0
        if "research_area" in used or "home_news" in used:
            answer, cited = tavily_tool.link_citations(answer, self.sources, self.lang)
            tool_text += "\n".join(src["url"] for src in self.sources.values())
        answer, report = guards.apply(answer, tool_text, self.lang, used)
        report["citations_linked"] = cited
        turn_msgs.append({"role": "assistant", "content": answer})
        self.history += turn_msgs
        self.done.add(suggest.norm(text))
        suggestions = self._suggestions(skill.name, text)
        yield {"type": "answer", "text": answer, "skill": skill.name, "lang": self.lang,
               "guards": report, "latency_s": round(time.monotonic() - t0, 2), "stats": dict(self.stats),
               "timings": list(self.timings), "listings": list(self.cards), "inventory": self.bars,
               "similar": self.similar, "suggestions": suggestions,
               "price_history": self.price_history, "x_url": self.x_url, "x_posts": self.x_posts}

    def _suggestions(self, skill: str, text: str) -> list[str]:
        """Up to three next questions for buttons under the answer (agent/suggest.py)."""
        places = list(self.filter.location) if self.filter and self.filter.location else []
        if skill == "compare-areas" and self.area_places:
            places = self.area_places
        focus = None
        if skill in ("check-asking-price", "contact-agent", "home-news"):
            focus = ordinals.ordinal(text, len(self.shown))
        cap = ((self.inventory or {}).get("args") or {}).get("max_price") if skill == "compare-budget" else None
        if skill == "find-homes" and self.sale_only:
            return [suggest.for_sale(self.lang, p) for p in self.sale_only[:suggest.MAX]]
        return suggest.next_questions(skill, self.lang, places=places,
                                      max_price=self.filter.max_price if self.filter else None,
                                      shown=self.shown, focus_n=focus, budget_cap=cap, done=self.done)
