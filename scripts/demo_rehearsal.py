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
    "How do I contact the agent for #2?",
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
    for i, msg in enumerate(TURNS, 1):
        session, out = turn(base, msg, session)
        ans = out["answer"] or {}
        cards = len(ans.get("listings") or [])
        print(f"\n[{i}] {msg}\n    {out['seconds']}s · lang={ans.get('lang')} · cards={cards} · filter={ans.get('filter')!r}")
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
