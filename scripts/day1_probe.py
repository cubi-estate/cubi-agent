"""Day-1 go/no-go probe: can Nemotron on Token Factory do what cubi-agent needs?

Checks, per model (nano / super / ultra):
  1. the model id is served (GET /v1/models);
  2. structured extraction: NL query → SearchFilter via response_format=json_schema
     (falls back to json_object + schema-in-prompt, and records which mode worked);
  3. tool calling: picks filter_listings with valid arguments for a plain request;
  4. (super only, with --live-loop) one full loop against the live Cubi connector,
     checking every listing URL in the answer appears verbatim in the tool output.

Writes reports/day1_<UTC timestamp>.json and .md.

  python scripts/day1_probe.py                # all checks
  python scripts/day1_probe.py --models-only  # just list Nemotron ids
  python scripts/day1_probe.py --roles super --live-loop
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from agent import llm  # noqa: E402
from agent.mcp_client import CubiMCP  # noqa: E402
from agent.schema import SearchFilter, strict_json_schema  # noqa: E402

REPORTS = Path(__file__).resolve().parent.parent / "reports"

EXTRACT_SYSTEM = (
    "You turn a home-search request into a search filter for a European property "
    "search service. Fill every field; use null or an empty list when the user did "
    "not say. Prices are in EUR. Portuguese 'T1/T2/T3' means 1/2/3 bedrooms; "
    "Spanish 'piso' and Portuguese 'apartamento' mean apartment. "
    "Reply with the JSON object only."
)

# (query, gold) — gold lists only the fields the query pins down.
CASES = [
    ("2-bedroom apartment in Porto under 400k with a balcony",
     {"location": ["porto"], "type": ["apartment"], "transaction_type": "sale", "max_price": 400000,
      "min_bedrooms": 2, "features": ["balcony"], "lang": "en", "needs_free_text_search": False}),
    ("Ich suche ein Haus mit Pool in Faro, maximal 600.000 Euro, mindestens 3 Schlafzimmer",
     {"location": ["faro"], "type": ["house"], "transaction_type": "sale", "max_price": 600000,
      "min_bedrooms": 3, "features": ["pool"], "lang": "de", "needs_free_text_search": False}),
    ("Quero arrendar um T1 em Lisboa até 1500 euros por mês",
     {"location": ["lisboa|lisbon"], "transaction_type": "rent", "max_price": 1500,
      "min_bedrooms": 1, "lang": "pt", "needs_free_text_search": False}),
    ("Piso de 3 habitaciones en Valencia o Alicante, menos de 250.000 €, con garaje",
     {"location": ["valencia", "alicante"], "type": ["apartment"], "transaction_type": "sale",
      "max_price": 250000, "min_bedrooms": 3, "has_parking": True, "lang": "es"}),
    ("Une maison calme près de la plage en Algarve, budget 500 000 €",
     {"type": ["house"], "transaction_type": "sale", "max_price": 500000, "lang": "fr",
      "needs_free_text_search": True}),
    ("Appartement in Málaga huren, max 1200 per maand, 2 slaapkamers",
     {"location": ["malaga"], "type": ["apartment"], "transaction_type": "rent", "max_price": 1200,
      "min_bedrooms": 2, "lang": "nl"}),
]

TOOL_SYSTEM = (
    "You help people find homes for sale or rent in Europe using Cubi Estate's tools. "
    "When the user names towns or cities, call filter_listings with structured arguments "
    "(pass transaction_type='rent' for rentals). Use search_properties only for fuzzy "
    "requests a filter cannot express. Show listing URLs exactly as the tools return them."
)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def score(pred: dict, gold: dict) -> tuple[int, int, list[str]]:
    """Field-level match count. Lists: every gold item must be matched (alias 'a|b')."""
    hits, misses = 0, []
    for key, want in gold.items():
        got = pred.get(key)
        if isinstance(want, list):
            got_n = [_norm(x) for x in (got or [])]
            ok = all(any(any(alt in g for alt in w.split("|")) for g in got_n) for w in want)
        elif isinstance(want, float | int) and not isinstance(want, bool):
            ok = got is not None and abs(float(got) - want) < 0.5
        else:
            ok = got == want
        hits += ok
        if not ok:
            misses.append(f"{key}: want {want!r} got {got!r}")
    return hits, len(gold), misses


def list_models(cli) -> list[str]:
    return sorted(m.id for m in cli.models.list().data)


def extract(cli, model: str, query: str, a_no_think: bool = True) -> dict:
    schema = strict_json_schema()
    attempts = [
        ("json_schema", {"type": "json_schema",
                         "json_schema": {"name": "SearchFilter", "schema": schema, "strict": True}}),
        ("json_object", {"type": "json_object"}),
    ]
    last_err = None
    for mode, response_format in attempts:
        system = EXTRACT_SYSTEM
        if mode == "json_object":
            system += "\nJSON schema:\n" + json.dumps(schema)
        t0 = time.monotonic()
        try:
            r = cli.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": query}],
                response_format=response_format,
                temperature=0,
                max_tokens=1024,
                extra_body=llm.NO_THINK if a_no_think else None,
            )
        except Exception as e:  # unsupported response_format → try next mode
            last_err = f"{mode}: {type(e).__name__}: {str(e)[:200]}"
            continue
        latency = time.monotonic() - t0
        content = r.choices[0].message.content or ""
        raw = _strip_fences(content)
        try:
            parsed = SearchFilter.model_validate_json(raw)
            return {"mode": mode, "ok": True, "latency_s": round(latency, 2), "usage": _usage(r),
                    "pred": parsed.model_dump(), "error": last_err}
        except ValidationError as e:
            return {"mode": mode, "ok": False, "latency_s": round(latency, 2), "usage": _usage(r),
                    "raw": content[:600], "error": f"validation: {e.error_count()} errors"}
    return {"mode": None, "ok": False, "error": last_err}


def _strip_fences(s: str) -> str:
    s = re.sub(r"(?s)<think>.*?</think>", "", s).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    return (m.group(1) if m else s).strip()


def _usage(r) -> dict:
    u = getattr(r, "usage", None)
    return {"in": getattr(u, "prompt_tokens", None), "out": getattr(u, "completion_tokens", None)}


def tool_call(cli, model: str, tools: list[dict], query: str) -> dict:
    t0 = time.monotonic()
    try:
        r = cli.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": TOOL_SYSTEM}, {"role": "user", "content": query}],
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=2048,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
    msg = r.choices[0].message
    calls = msg.tool_calls or []
    out = {"latency_s": round(time.monotonic() - t0, 2), "usage": _usage(r), "n_calls": len(calls)}
    if not calls:
        out.update(ok=False, error="no tool call", content=(msg.content or "")[:300])
        return out
    c = calls[0]
    try:
        args = json.loads(c.function.arguments or "{}")
        args_ok = isinstance(args, dict)
    except json.JSONDecodeError:
        args, args_ok = c.function.arguments, False
    out.update(ok=args_ok and c.function.name == "filter_listings", tool=c.function.name, args=args)
    return out


def live_loop(cli, model: str, mcp: CubiMCP, tools: list[dict], query: str, max_steps: int = 4) -> dict:
    messages = [{"role": "system", "content": TOOL_SYSTEM}, {"role": "user", "content": query}]
    tool_text = ""
    trace = []
    t0 = time.monotonic()
    for _ in range(max_steps):
        r = cli.chat.completions.create(model=model, messages=messages, tools=tools,
                                        tool_choice="auto", temperature=0, max_tokens=3000)
        msg = r.choices[0].message
        if not msg.tool_calls:
            answer = msg.content or ""
            urls = re.findall(r"https?://[^\s)\]>\"']+", answer)
            bad = [u for u in urls if u.rstrip(".,;") not in tool_text]
            return {"ok": bool(urls) and not bad, "steps": trace, "n_urls": len(urls),
                    "unverified_urls": bad, "latency_s": round(time.monotonic() - t0, 2),
                    "answer_head": answer[:800]}
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            res = mcp.call_tool(tc.function.name, args)
            tool_text += res["text"]
            trace.append({"tool": tc.function.name, "args": args, "is_error": res["is_error"],
                          "chars": len(res["text"])})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": res["text"][:12000]})
    return {"ok": False, "steps": trace, "error": "step cap reached"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roles", default="nano,lightning,super,ultra")
    ap.add_argument("--models-only", action="store_true")
    ap.add_argument("--live-loop", action="store_true", help="run one full loop on the live connector (super)")
    a = ap.parse_args()

    cli = llm.client()
    served = list_models(cli)
    nemotron = [m for m in served if "nemotron" in m.lower()]
    report: dict = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "nemotron_served": nemotron, "roles": {}}
    print("Nemotron models served:", *nemotron, sep="\n  ")
    if a.models_only:
        return 0

    mcp = CubiMCP()
    tools = mcp.openai_tools(["filter_listings", "search_properties", "get_listing"])

    for role in a.roles.split(","):
        model = llm.model(role)
        entry: dict = {"model": model, "served": model in served, "extract": [], "tools": []}
        report["roles"][role] = entry
        print(f"\n== {role}: {model} (served={entry['served']})")
        if not entry["served"]:
            continue
        for query, gold in CASES:
            res = extract(cli, model, query)
            if res.get("ok"):
                res["hits"], res["of"], res["misses"] = score(res["pred"], gold)
            entry["extract"].append({"query": query, **res})
            print(f"  extract [{res.get('mode')}] ok={res.get('ok')} "
                  f"{res.get('hits', 0)}/{res.get('of', len(gold))} {res.get('latency_s')}s "
                  f"{'; '.join(res.get('misses', [])) or res.get('error') or ''}")
        for query, _ in CASES[:3]:
            res = tool_call(cli, model, tools, query)
            entry["tools"].append({"query": query, **res})
            print(f"  tools ok={res.get('ok')} {res.get('tool')} {res.get('latency_s')}s {res.get('error', '')}")
        if a.live_loop and role == "super":
            entry["live_loop"] = live_loop(cli, model, mcp, tools, CASES[0][0])
            print("  live loop:", {k: v for k, v in entry["live_loop"].items() if k != "answer_head"})

    REPORTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (REPORTS / f"day1_{stamp}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (REPORTS / f"day1_{stamp}.md").write_text(render_md(report))
    print(f"\nreport: reports/day1_{stamp}.md")
    return 0


def render_md(report: dict) -> str:
    lines = [f"# Day-1 probe — {report['at']}", "", "Nemotron models served: "
             + ", ".join(f"`{m}`" for m in report["nemotron_served"]), "",
             "| role | model | served | extraction valid | field accuracy | mode | median latency | tool call ok |",
             "|---|---|---|---|---|---|---|---|"]
    for role, e in report["roles"].items():
        ex, tl = e["extract"], e["tools"]
        valid = sum(x.get("ok", False) for x in ex)
        hits = sum(x.get("hits", 0) for x in ex)
        of = sum(x.get("of", 0) for x in ex if x.get("ok")) or 0
        lat = sorted(x["latency_s"] for x in ex if x.get("latency_s") is not None)
        modes = sorted({x.get("mode") for x in ex if x.get("mode")})
        lines.append(
            f"| {role} | `{e['model']}` | {e['served']} | {valid}/{len(ex)} | "
            f"{hits}/{of} | {', '.join(modes) or '-'} | {lat[len(lat)//2] if lat else '-'}s | "
            f"{sum(x.get('ok', False) for x in tl)}/{len(tl)} |")
    for role, e in report["roles"].items():
        misses = [(x["query"], m) for x in e["extract"] for m in x.get("misses", [])]
        errs = [(x["query"], x.get("error")) for x in e["extract"] + e["tools"] if not x.get("ok")]
        if misses or errs:
            lines += ["", f"## {role} — misses", ""]
            lines += [f"- {q[:60]} — {m}" for q, m in misses]
            lines += [f"- {q[:60]} — ERROR {err}" for q, err in errs if err]
        if "live_loop" in e:
            ll = e["live_loop"]
            lines += ["", f"## {role} — live loop", "", f"ok={ll.get('ok')} steps={ll.get('steps')} "
                      f"urls={ll.get('n_urls')} unverified={ll.get('unverified_urls')} latency={ll.get('latency_s')}s"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
