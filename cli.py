"""Chat with cubi-agent in the terminal.

  python cli.py                                   # interactive
  python cli.py "2-bed in Porto under 400k" "is the first one overpriced?"   # scripted turns
"""
from __future__ import annotations

import sys

from agent.listings import places
from agent.loop import Agent


def card_line(c: dict) -> str:
    place = ", ".join(places(c.get("location", ""))[:2])
    bits = [f"#{c['n']}", c.get("type", "Home"), place, c.get("price_text", "price n/a")]
    if c.get("bedrooms") is not None:
        bits.append(f"{c['bedrooms']:.0f} bd")
    if c.get("living_area") is not None:
        bits.append(f"{c['living_area']:.0f} m²")
    return " · ".join(b for b in bits if b) + f"\n     {c.get('url', '')}"


def run(turns: list[str], timings: bool = False) -> None:
    agent = Agent()
    interactive = not turns
    while True:
        if interactive:
            try:
                text = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not text:
                continue
        else:
            if not turns:
                return
            text = turns.pop(0)
            print(f"\nyou> {text}")
        for ev in agent.turn(text):
            if ev["type"] == "action":
                print(f"  · {ev['text']}")
            elif ev["type"] == "answer":
                print(f"\ncubi> {ev['text']}")
                for c in ev.get("listings", []):
                    print("  " + card_line(c))
                g = ev["guards"]
                print(f"  [{ev['skill']} · {ev['lang']} · {ev['latency_s']}s · tokens in/out "
                      f"{ev['stats']['llm_in']}/{ev['stats']['llm_out']} · urls removed "
                      f"{len(g['urls_removed'])} · fallback searches {ev['stats']['fallback_searches']}]")
                if timings:
                    print("  timings: " + " · ".join(f"{name} {s}s" for name, s in ev["timings"]))


if __name__ == "__main__":
    args = sys.argv[1:]
    show = "--timings" in args
    run([a for a in args if a != "--timings"], timings=show)
