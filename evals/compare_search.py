"""Does the agent's search path beat sending the request straight to Cubi's free-text search?

For each request the agent would route to the structured filter, run both:

  agent   Nemotron extraction + normalise → `filter_listings`
  direct  the raw request → `search_properties` (Cubi's own OpenAI-based NLU)

and check every returned listing against the gold constraints that a card
shows: price bounds, minimum bedrooms, property type and place. Also latency,
errors and the connector quota units each path spends.

  python evals/compare_search.py                     # held-out set, filter-route cases
  python evals/compare_search.py --ids h_en01,h_pt03 --limit 6

Writes reports/compare_<UTC>.md (and .json, git-ignored: it holds listing facts).
Costs about 11 quota units per case against the anonymous daily budget of 500.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import listings, llm  # noqa: E402
from agent.extract import extract  # noqa: E402
from agent.mcp_client import CubiMCP  # noqa: E402

HELDOUT = ROOT / "evals" / "filter_extraction_heldout.jsonl"
TYPE_WORDS = {  # gold type → words a card's type label may use (cards keep some source-language labels)
    "apartment": ("apartment", "flat", "duplex", "piso", "apartamento", "appartement", "wohnung", "appartamento",
                  "portiekwoning", "benedenwoning", "bovenwoning", "maisonnette"),
    "house": ("house", "villa", "townhouse", "chalet", "cottage", "bungalow", "farmhouse", "moradia", "casa",
              "maison", "haus", "huis", "woning"),
    "villa": ("villa", "house", "chalet", "moradia"),
    "penthouse": ("penthouse", "atico", "attico", "cobertura"),
    "studio": ("studio", "estudio", "monolocale"),
    "land": ("land", "plot", "terreno", "terrain", "grundstuck", "grond"),
}


def _plain(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def check(card: dict, gold: dict) -> dict[str, bool | None]:
    """Per constraint: True/False, or None when the card doesn't show it."""
    out: dict[str, bool | None] = {}
    price = card.get("price")
    if "max_price" in gold:
        out["max_price"] = None if price is None else price <= gold["max_price"]
    if "min_price" in gold:
        out["min_price"] = None if price is None else price >= gold["min_price"]
    if "min_bedrooms" in gold:
        beds = card.get("bedrooms")
        out["min_bedrooms"] = None if beds is None else beds >= gold["min_bedrooms"]
    if "type" in gold:
        label = _plain(card.get("type", ""))
        wanted = {w for g in gold["type"] for alt in g.split("|") for w in TYPE_WORDS.get(alt, (alt,))}
        out["type"] = None if not label else any(w in label for w in wanted)
    if "location" in gold:
        place = _plain(card.get("location", ""))
        out["location"] = None if not place else all(
            any(alt in place for alt in g.split("|")) for g in gold["location"])
    return out


_last_call = [0.0]
MIN_GAP_S = 2.1  # the connector allows 30 tool calls a minute per client


def run_path(mcp: CubiMCP, tool: str, args: dict) -> dict:
    wait = MIN_GAP_S - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()
    n0 = len(mcp.calls)
    t0 = time.monotonic()
    try:
        res = mcp.call_tool(tool, args)
        text, err = res["text"], res["is_error"]
    except Exception as e:  # noqa: BLE001 — a failed path is a result here
        text, err = f"error: {e}", True
    return {"tool": tool, "seconds": round(time.monotonic() - t0, 2), "is_error": err,
            "units": sum(c["units"] for c in mcp.calls[n0:]), "cards": [] if err else listings.parse(text),
            "header": listings.header(text)[:300]}


def score_cards(cards: list[dict], gold: dict) -> dict:
    checks = [check(c, gold) for c in cards]
    known = [v for ch in checks for v in ch.values() if v is not None]
    return {
        "returned": len(cards),
        "all_ok": sum(all(v is not False for v in ch.values()) for ch in checks),
        "violations": sum(v is False for v in known),
        "checked": len(known),
        "by_field": {k: sum(ch.get(k) is False for ch in checks) for k in {k for ch in checks for k in ch}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HELDOUT))
    ap.add_argument("--ids", default="")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--reuse-direct", default="", help="take the direct side from an earlier compare_*.json "
                                                       "(saves 10 quota units per case)")
    a = ap.parse_args()
    earlier = {r["id"]: r["direct"] for r in json.loads(Path(a.reuse_direct).read_text())} if a.reuse_direct else {}
    cases = [json.loads(line) for line in Path(a.cases).read_text().splitlines() if line.strip()]
    cases = [c for c in cases if c["route"] == "filter"]
    if a.ids:
        wanted = set(a.ids.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    cli, mcp = llm.client(), CubiMCP()
    rows = []
    for c in cases:
        ex = extract(c["q"], cli=cli)
        if ex.filter is None or ex.route != "filter":
            agent = {"tool": "search_properties", "skipped": "extraction routed to free text", "cards": []}
        else:
            args = ex.filter.to_filter_args(limit=a.limit)
            agent = run_path(mcp, "filter_listings", args)
            if not agent["is_error"] and not agent["cards"] and args.get("features"):  # as agent/loop.py
                args.pop("features")
                relaxed = run_path(mcp, "filter_listings", args)
                relaxed["seconds"] = round(relaxed["seconds"] + agent["seconds"], 2)
                relaxed["units"] += agent["units"]
                agent = {**relaxed, "relaxed": True}
            agent["seconds"] = round(agent["seconds"] + ex.latency_s, 2)
            agent["extract_s"] = ex.latency_s
        direct = earlier.get(c["id"]) or run_path(mcp, "search_properties",
                                                  {"query": c["q"], "lang": c["lang"], "limit": a.limit})
        row = {"id": c["id"], "q": c["q"], "agent": agent, "direct": direct,
               "agent_score": score_cards(agent["cards"], c["gold"]),
               "direct_score": score_cards(direct["cards"], c["gold"])}
        rows.append(row)
        sa, sd = row["agent_score"], row["direct_score"]
        print(f"  {c['id']}: agent {sa['all_ok']}/{sa['returned']} ok {agent.get('seconds')}s"
              f"{' ERR' if agent.get('is_error') else ''} | direct {sd['all_ok']}/{sd['returned']} ok "
              f"{direct['seconds']}s{' ERR' if direct['is_error'] else ''}")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md = render(rows, Path(a.cases).name, a.limit)
    if a.reuse_direct:
        md = md.replace("\n\n|", f"\n\nDirect side reused from `{Path(a.reuse_direct).name}`.\n\n|", 1)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / f"compare_{stamp}.md").write_text(md)
    (ROOT / "reports" / f"compare_{stamp}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print("\n" + md)
    print(f"report: reports/compare_{stamp}.md")
    return 0


def _side(rows: list[dict], key: str) -> dict:
    runs = [r[key] for r in rows if not r[key].get("skipped")]
    scores = [r[f"{key}_score"] for r in rows if not r[key].get("skipped")]
    secs = [x["seconds"] for x in runs]
    fields: dict[str, int] = {}
    for s in scores:
        for k, v in s["by_field"].items():
            fields[k] = fields.get(k, 0) + v
    return {
        "runs": len(runs), "errors": sum(bool(x.get("is_error")) for x in runs),
        "empty": sum(s["returned"] == 0 for s, x in zip(scores, runs) if not x.get("is_error")),
        "returned": sum(s["returned"] for s in scores), "all_ok": sum(s["all_ok"] for s in scores),
        "violations": sum(s["violations"] for s in scores), "checked": sum(s["checked"] for s in scores),
        "p50": round(statistics.median(secs), 2) if secs else 0,
        "max": max(secs) if secs else 0, "units": sum(x.get("units", 0) for x in runs), "fields": fields,
    }


def render(rows: list[dict], set_name: str, limit: int) -> str:
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    A, D = _side(rows, "agent"), _side(rows, "direct")
    skipped = sum(bool(r["agent"].get("skipped")) for r in rows)

    def pct(s):
        return f"{s['all_ok']}/{s['returned']} ({100 * s['all_ok'] / max(1, s['returned']):.0f}%)"

    out = [f"# Agent search vs direct free-text search — {at}", "",
           f"`evals/{set_name}`, the {len(rows)} requests the agent sends to the structured filter, "
           f"limit {limit}. Agent = Nemotron Super extraction → `filter_listings` (on zero results, once more without features, as the agent does). Direct = the raw "
           f"request → `search_properties`. A listing is *ok* when no constraint visible on its card "
           f"(price bounds, min bedrooms, type, place) is broken; features and sale/rent aren't on the card "
           f"and aren't checked." + (f" {skipped} request(s) were routed to free text by the agent and "
                                     f"are left out of its column." if skipped else ""), "",
           "| | agent | direct |", "|---|---|---|",
           f"| runs (errors) | {A['runs']} ({A['errors']}) | {D['runs']} ({D['errors']}) |",
           f"| no results | {A['empty']} | {D['empty']} |",
           f"| listings meeting every visible constraint | {pct(A)} | {pct(D)} |",
           f"| constraint violations / checks | {A['violations']}/{A['checked']} | {D['violations']}/{D['checked']} |",
           f"| latency p50 / max (agent incl. extraction) | {A['p50']}s / {A['max']}s | {D['p50']}s / {D['max']}s |",
           f"| connector quota units | {A['units']} | {D['units']} |", "",
           "Violations by constraint: agent " + json.dumps(A["fields"]) + ", direct " + json.dumps(D["fields"]), "",
           "| id | request | agent ok/returned | direct ok/returned |", "|---|---|---|---|"]
    for r in rows:
        sa, sd = r["agent_score"], r["direct_score"]
        a_cell = "skipped" if r["agent"].get("skipped") else (
            "error" if r["agent"].get("is_error") else f"{sa['all_ok']}/{sa['returned']}")
        d_cell = "error" if r["direct"]["is_error"] else f"{sd['all_ok']}/{sd['returned']}"
        out.append(f"| `{r['id']}` | {r['q']} | {a_cell} | {d_cell} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
