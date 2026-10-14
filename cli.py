"""Chat with cubi-agent in the terminal.

  python cli.py                                   # interactive
  python cli.py "2-bed in Porto under 400k" "is the first one overpriced?"   # scripted turns
"""
from __future__ import annotations

import sys

from agent.loop import Agent


def run(turns: list[str]) -> None:
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
                g = ev["guards"]
                print(f"  [{ev['skill']} · {ev['lang']} · {ev['latency_s']}s · tokens in/out "
                      f"{ev['stats']['llm_in']}/{ev['stats']['llm_out']} · urls removed "
                      f"{len(g['urls_removed'])} · fallback searches {ev['stats']['fallback_searches']}]")


if __name__ == "__main__":
    run(sys.argv[1:])
