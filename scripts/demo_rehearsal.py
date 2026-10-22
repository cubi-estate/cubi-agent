"""Run the video's demo turns against a deployed agent and report what each turn did.

    python scripts/demo_rehearsal.py [--url https://www.cubi.estate/agent] [--show-text]

One session, the turns in order, as the page sends them. Prints per turn: the
action log, how many cards came back, the language and the seconds taken. With
--show-text it also prints the answer text (listing facts from the connector).
Uses about 5 of the demo's turns and a few connector quota units.
"""
import argparse
import json
import sys
import time
import urllib.request

TURNS = [
    "Wir ziehen um: Wohnung zum Kauf in Porto oder Valencia, bis 400.000 €, mindestens 2 Schlafzimmer",
    "Is #2 overpriced?",
    "Compare schools and public transport in Porto and Valencia",
    "What does 400k buy in Lisbon vs Porto? 2-bed flats",
    "And up to 500k?",
    "<feature by feature>",  # not in the video: clicks the leaders suggestion the last answer offered
    "How do I contact the agent for #2?",
    "Show me homes like #2 in Porto",  # not in the video: the side-by-side table
]


def resolve(url: str) -> str:
    # https://www.cubi.estate/agent is a redirect; post to where it points.
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.url.rstrip("/")


def turn(base: str, message: str, session: str | None) -> tuple[str | None, dict]:
    body = json.dumps({"message": message, "session_id": session}).encode()
    req = urllib.request.Request(f"{base}/api/chat", data=body, headers={"Content-Type": "application/json"})
    out = {"actions": [], "errors": [], "answer": None}
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=120) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev["type"] == "session":
                session = ev["id"]
            elif ev["type"] == "action":
                out["actions"].append(ev["text"])
            elif ev["type"] == "error":
                out["errors"].append(ev["text"])
            elif ev["type"] == "answer":
                out["answer"] = ev
    out["seconds"] = round(time.monotonic() - t0, 1)
    return session, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://www.cubi.estate/agent")
    ap.add_argument("--show-text", action="store_true")
    a = ap.parse_args()
    base = resolve(a.url)
    with urllib.request.urlopen(f"{base}/api/health", timeout=20) as r:
        print("health", r.read().decode())
    session, ok = None, True
    last: dict = {}
    for i, msg in enumerate(TURNS, 1):
        if msg.startswith("<"):
            # Follow the suggestion the page would show, like a user clicking it.
            msg = next((q for q in last.get("suggestions") or [] if msg.strip("<>") in q), None)
            if msg is None:
                print(f"\n[{i}] ! no suggestion matching {TURNS[i - 1]!r} — skipped")
                ok = False
                continue
        session, out = turn(base, msg, session)
        last = out["answer"] or {}
        ans = out["answer"] or {}
        cards = len(ans.get("listings") or [])
        print(f"\n[{i}] {msg}\n    {out['seconds']}s · lang={ans.get('lang')} · cards={cards} · filter={ans.get('filter')!r}")
        for r in (ans.get("inventory") or {}).get("rows", []):
            was = f" (was {r['previous_pct']}%)" if r.get("previous_pct") is not None else ""
            print(f"    ▮ {r['place']}: {r.get('share_pct')}% · {r.get('within')} of {r.get('of')}{was}")
        sim = ans.get("similar") or {}
        for c in sim.get("columns", []):
            env = sum(1 for a in (c.get("environment") or {}).values() if a.get("state") != "unknown")
            feats = [k for k, v in (c.get("features") or {}).items() if v == "stated"]
            print(f"    ▤ {c['role']} #{c.get('card')} {c.get('city')}: €{c.get('price') or 0:,.0f} · "
                  f"{env}/8 environment readings · stated: {', '.join(feats) or '—'}")
        for q in ans.get("suggestions") or []:
            print(f"    → {q}")
        for s in out["actions"]:
            print("    ·", s)
        for e in out["errors"]:
            print("    ! error:", e)
            ok = False
        if not ans:
            ok = False
        if a.show_text and ans:
            print("    ---\n    " + (ans.get("text") or "").replace("\n", "\n    "))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
