"""Filter-extraction eval: which Nemotron model should turn requests into filters?

For each model: valid-output rate, repair-retry rate, field accuracy (overall and
per field), route accuracy under two routing rules, latency p50/p95, tokens, and
cost where the price is known. Language is scored for the deterministic detector
(agent/lang.py), which the agent uses instead of the model's guess.

  python evals/run_eval.py                       # nano,lightning,super,ultra
  python evals/run_eval.py --roles nano,super --ids en01,pt05

Writes reports/eval_<UTC>.md (and .json, git-ignored).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import lang as langmod  # noqa: E402
from agent import llm  # noqa: E402
from agent import normalize  # noqa: E402
from agent.extract import extract  # noqa: E402
from scripts.day1_probe import score  # noqa: E402

CASES = ROOT / "evals" / "filter_extraction.jsonl"
# USD per million tokens (input, output), from the Token Factory catalogue.
# None = not checked yet; the report then shows tokens only.
PRICES = {
    "super": (0.30, 0.90),
    "ultra": (1.00, 3.00),
    "nano": None,
    "lightning": None,
}


def route_a(f) -> str:  # what the agent does: place named and no free-text cue (agent/normalize.py)
    return normalize.route_for(f)


def route_b(f) -> str:  # baseline: any place named → structured filter
    return "filter" if f is not None and f.location else "search"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else 0.0


def run_role(cli, role: str, cases: list[dict]) -> dict:
    rows = []
    for c in cases:
        ex = extract(c["q"], role=role, cli=cli)
        pred = ex.filter.model_dump() if ex.filter else None
        hits, of, misses = score(pred, c["gold"]) if pred else (0, len(c["gold"]), ["invalid output"])
        per_field = {}
        for key in c["gold"]:
            per_field[key] = pred is not None and not any(m.startswith(f"{key}:") for m in misses)
        rows.append({
            "id": c["id"], "valid": pred is not None, "attempts": ex.attempts, "hits": hits, "of": of,
            "misses": misses, "per_field": per_field, "latency_s": ex.latency_s, "usage": ex.usage,
            "route_a": route_a(ex.filter) == c["route"], "route_b": route_b(ex.filter) == c["route"],
            "error": ex.error,
        })
        print(f"  {role:9} {c['id']} {hits}/{of} {ex.latency_s}s {'; '.join(misses)[:140]}")
    return {"model": llm.model(role), "rows": rows}


def summarise(role: str, res: dict) -> dict:
    rows = res["rows"]
    lat = [r["latency_s"] for r in rows]
    tin = sum(r["usage"].get("in", 0) for r in rows)
    tout = sum(r["usage"].get("out", 0) for r in rows)
    price = PRICES.get(role)
    cost_per_1k = (1000 / len(rows)) * (tin * price[0] + tout * price[1]) / 1e6 if price else None
    fields = defaultdict(lambda: [0, 0])
    for r in rows:
        for k, ok in r["per_field"].items():
            fields[k][0] += ok
            fields[k][1] += 1
    return {
        "role": role, "model": res["model"], "n": len(rows),
        "valid": sum(r["valid"] for r in rows), "retried": sum(r["attempts"] > 1 for r in rows),
        "hits": sum(r["hits"] for r in rows), "of": sum(r["of"] for r in rows),
        "exact": sum(r["hits"] == r["of"] for r in rows),
        "route_a": sum(r["route_a"] for r in rows), "route_b": sum(r["route_b"] for r in rows),
        "p50": round(statistics.median(lat), 2), "p95": round(pct(lat, 0.95), 2),
        "tokens_in": tin, "tokens_out": tout, "usd_per_1k_queries": cost_per_1k,
        "fields": {k: f"{v[0]}/{v[1]}" for k, v in sorted(fields.items())},
    }


def render(summary: list[dict], lang_ok: int, n: int, results: dict, at: str) -> str:
    out = [f"# Filter-extraction eval — {at}", "",
           f"{n} requests, 10 per language (en/pt/es/fr/de/nl), single turn. Thinking off. "
           f"Model output passes through agent/normalize.py (as in the agent). "
           f"Gold in `evals/filter_extraction.jsonl`.", "",
           f"Deterministic language detector: **{lang_ok}/{n}** correct.", "",
           "| role | model | valid | retried | field acc | all fields right | route (agent rule) | route (place only) | p50 | p95 | $/1k queries |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        usd = f"{s['usd_per_1k_queries']:.2f}" if s["usd_per_1k_queries"] is not None else "n/a"
        out.append(f"| {s['role']} | `{s['model']}` | {s['valid']}/{s['n']} | {s['retried']} | "
                   f"{s['hits']}/{s['of']} ({100*s['hits']/max(1,s['of']):.1f}%) | {s['exact']}/{s['n']} | "
                   f"{s['route_a']}/{s['n']} | {s['route_b']}/{s['n']} | {s['p50']}s | {s['p95']}s | {usd} |")
    keys = sorted({k for s in summary for k in s["fields"]})
    out += ["", "## Per field", "", "| field | " + " | ".join(s["role"] for s in summary) + " |",
            "|---|" + "---|" * len(summary)]
    for k in keys:
        out.append(f"| {k} | " + " | ".join(s["fields"].get(k, "-") for s in summary) + " |")
    for s in summary:
        misses = [(r["id"], m) for r in results[s["role"]]["rows"] for m in r["misses"]]
        if misses:
            out += ["", f"## {s['role']} — misses", ""] + [f"- `{i}` {m}" for i, m in misses]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roles", default="nano,lightning,super,ultra")
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    if a.ids:
        wanted = set(a.ids.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    lang_ok = sum(langmod.detect(c["q"]) == c["lang"] for c in cases)
    for c in cases:
        if langmod.detect(c["q"]) != c["lang"]:
            print(f"  lang miss {c['id']}: detected {langmod.detect(c['q'])}")
    cli = llm.client()
    results = {role: run_role(cli, role, cases) for role in a.roles.split(",")}
    summary = [summarise(role, res) for role, res in results.items()]
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (ROOT / "reports").mkdir(exist_ok=True)
    md = render(summary, lang_ok, len(cases), results, at)
    (ROOT / "reports" / f"eval_{stamp}.md").write_text(md)
    (ROOT / "reports" / f"eval_{stamp}.json").write_text(json.dumps({"summary": summary, "results": results}, indent=1))
    print("\n" + md.split("## Per field")[0])
    print(f"report: reports/eval_{stamp}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
