"""Load the shared skill pack (SKILL.md files) and pick one per turn.

The same files drive the Cubi Estate plugin for Claude; here they become the
system prompt for Nemotron. Selection is a cheap keyword rule, not a model
call: ambiguous messages go to `find-homes`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "vendor" / "cubi-estate-plugin" / "skills"

# Tools each skill may use (task-scoped, per the plan).
TOOLS = {
    # search_homes is local: Nemotron extraction → filter_listings, or the
    # free-text search_properties fallback (see agent/extract.py).
    "find-homes": ["search_homes", "get_listing"],
    "check-asking-price": ["compare_asking_prices", "get_listing"],
    "contact-agent": ["get_contact_options"],
}

_PATTERNS = {
    "check-asking-price": r"overpric|expensive|cheap|good deal|fair price|price compar|worth|"
                          r"caro|barato|vale a pena|preço justo|precio justo|"
                          r"teuer|günstig|preiswert|zu viel|cher|bon prix|trop|duur|goedkoop",
    "contact-agent": r"contact|agent|viewing|visit|call|phone|email|"
                     r"contactar|agente|visita|ligar|telefone|llamar|"
                     r"kontakt|makler|besichtig|anrufen|contacter|visiter|appeler|"
                     r"makelaar|bezichtig|bellen",
}


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str

    @property
    def tools(self) -> list[str]:
        return TOOLS[self.name]


def _parse(path: Path) -> Skill:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    meta, body = (m.group(1), m.group(2)) if m else ("", text)
    fields = dict(re.findall(r"^(\w+):\s*(.*)$", meta, re.M))
    return Skill(fields.get("name", path.parent.name), fields.get("description", ""), body.strip())


def load(skills_dir: Path = SKILLS_DIR) -> dict[str, Skill]:
    if not skills_dir.exists():
        raise FileNotFoundError(
            f"{skills_dir} missing — run `git submodule update --init` to fetch the skill pack"
        )
    out = {}
    for p in sorted(skills_dir.glob("*/SKILL.md")):
        s = _parse(p)
        if s.name in TOOLS:
            out[s.name] = s
    return out


def select(message: str, has_results: bool) -> str:
    """Pick a skill. Price/contact questions only make sense about a home already shown."""
    low = message.lower()
    if has_results:
        for name in ("check-asking-price", "contact-agent"):
            if re.search(_PATTERNS[name], low):
                return name
    return "find-homes"
