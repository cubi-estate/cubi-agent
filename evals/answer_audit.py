"""How often does the loop model describe homes the tools never returned?

Runs one fresh first turn per request through the full agent and records what
the deterministic guards had to remove: unverified URLs, whole list items
(invented listings), scrubbed contact details. Homes are shown as cards built
from the tool output, so the model's text is a short summary. Also the stage timings, to see
where a first turn's time goes.

  python evals/answer_audit.py                 # held-out set, filter-route cases
  python evals/answer_audit.py --n 10

Writes reports/audit_<UTC>.md (.json git-ignored: it holds the answers).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.loop import LOOP_ROLE, Agent  # noqa: E402
from agent import llm  # noqa: E402

HELDOUT = ROOT / "evals" / "filter_extraction_heldout.jsonl"


def _stage(name: str) -> str:
    return re.sub(r"\s*\(.*\)$", "", re.sub(r"loop step \d+", "loop step", name))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HELDOUT))
    ap.add_argument("--n", type=int, default=0, help="first N cases only")
    a = ap.parse_args()
    cases = [json.loads(line) for line in Path(a.cases).read_text().splitlines() if line.strip()]
    cases = [c for c in cases if c["route"] == "filter"]
    if a.n:
        cases = cases[: a.n]

    rows = []
    for c in cases:
        agent = Agent()
        ev = next(e for e in agent.turn(c["q"]) if e["type"] == "answer")
        g = ev["guards"]
        verified = len(ev.get("listings", []))
        rows.append({"id": c["id"], "lang": ev["lang"], "latency_s": ev["latency_s"], "timings": ev["timings"],
                     "urls_removed": len(g["urls_removed"]), "items_dropped": g["items_dropped"],
                     "contacts_scrubbed": g["contacts_scrubbed"], "cards": verified,
                     "tokens_out": ev["stats"]["llm_out"], "answer": ev["text"]})
        print(f"  {c['id']} {ev['latency_s']}s dropped {g['items_dropped']} urls removed "
              f"{len(g['urls_removed'])} cards {verified}")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md = render(rows, Path(a.cases).name)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / f"audit_{stamp}.md").write_text(md)
    (ROOT / "reports" / f"audit_{stamp}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print("\n" + md)
    print(f"report: reports/audit_{stamp}.md")
    return 0


def render(rows: list[dict], set_name: str) -> str:
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    n = len(rows)
    lat = [r["latency_s"] for r in rows]
    stage = defaultdict(list)
    for r in rows:
        per: dict[str, float] = defaultdict(float)
        for name, s in r["timings"]:
            per[_stage(name)] += s
        for k, v in per.items():
            stage[k].append(v)
    bad = [r for r in rows if r["items_dropped"] or r["urls_removed"]]
    out = [f"# Answer audit — {at}", "",
           f"`evals/{set_name}`, {n} filter-route requests, one fresh first turn each, loop model "
           f"`{llm.model(LOOP_ROLE)}`, thinking off.", "",
           "| | |", "|---|---|",
           f"| answers needing a guard fix | {len(bad)}/{n} |",
           f"| invented list items dropped | {sum(r['items_dropped'] for r in rows)} |",
           f"| unverified URLs removed | {sum(r['urls_removed'] for r in rows)} |",
           f"| contact details scrubbed | {sum(r['contacts_scrubbed'] for r in rows)} |",
           f"| listing cards shown (rendered from tool output), median | {statistics.median(r['cards'] for r in rows)} |",
           f"| first-turn latency p50 / max | {statistics.median(lat):.2f}s / {max(lat):.2f}s |",
           f"| tokens out per turn, median | {statistics.median(r['tokens_out'] for r in rows)} |", "",
           "## Where a first turn's time goes (median seconds per turn)", "",
           "| stage | p50 | max |", "|---|---|---|"]
    for k, v in sorted(stage.items(), key=lambda kv: -statistics.median(kv[1])):
        out.append(f"| {k} | {statistics.median(v):.2f} | {max(v):.2f} |")
    if bad:
        out += ["", "## Turns the guards had to fix", ""]
        out += [f"- `{r['id']}` ({r['lang']}): {r['items_dropped']} item(s) dropped, "
                f"{r['urls_removed']} URL(s) removed" for r in bad]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
