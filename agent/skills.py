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
# Skills this app adds on top of the shared pack (they need tools the plugin lacks).
LOCAL_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Tools each skill may use (task-scoped, per the plan).
TOOLS = {
    # search_homes is local: Nemotron extraction → filter_listings, or the
    # free-text search_properties fallback (see agent/extract.py).
    "find-homes": ["search_homes", "get_listing"],
    "check-asking-price": ["compare_asking_prices", "get_listing"],
    "contact-agent": ["get_contact_options"],
    "compare-areas": ["research_area"],  # local tool: Tavily web search (agent/tavily_tool.py)
    # Run in code before the model writes (agent/inventory.py), like a search turn.
    "compare-budget": ["compare_inventory"],
    "similar-elsewhere": ["find_similar_elsewhere"],
}

_PATTERNS = {
    # "in line with" phrasings are the suggested next questions (agent/suggest.py).
    "check-asking-price": r"overpric|expensive|cheap|good deal|fair price|price compar|worth|"
                          r"price in line|in line with|em linha com|en l[ií]nea con|im rahmen|"
                          r"coh[ée]rent avec|in lijn met|"
                          r"caro|barato|vale a pena|preço justo|precio justo|"
                          r"teuer|günstig|preiswert|zu viel|cher|bon prix|trop|duur|goedkoop",
    "contact-agent": r"contact|agent|viewing|visit|call|phone|email|"
                     r"contactar|agente|visita|ligar|telefone|llamar|"
                     r"kontakt|makler|besichtig|anrufen|contacter|visiter|appeler|"
                     r"makelaar|bezichtig|bellen",
    # Living-in-the-area topics; a bare "compare" is not enough (it may be prices or homes).
    "compare-areas": r"school|escola|colegio|escuela|[ée]cole|schule|scholen|school|"
                     r"transport|metro|tram|bus\b|commut|"
                     r"safety|safe\b|crime|segura|seguridad|s[ée]curit|sicher|veilig|"
                     r"hospital|healthcare|sa[uú]de|sanidad|sant[ée]\b|gesundheit|zorg|"
                     r"quality of life|qualidade de vida|calidad de vida|qualit[ée] de vie|lebensqualit|"
                     r"kwaliteit van leven|cost of living|custo de vida|coste de vida|co[uû]t de la vie|"
                     r"lebenshaltung|kosten van levensonderhoud|neighbou?rhood|bairro|barrio|quartier|"
                     r"viertel|buurt|which (town|city|area) is better|live in",
    # What money buys across places — an analytic question, not a search. Phrased
    # narrowly on purpose: "Porto or Valencia, up to 400k" is a home search.
    "compare-budget": r"what (does|do|can|would|will) .{0,60}\bbuys?\b|how far does .{0,40}\bgo\b|"
                      r"\bafford\b|share of (homes|flats|apartments|listings)|"
                      r"o que (se )?compr[ao]|quanto (se )?compr[ao]|qu[eé] (se )?(puede )?compr[ao]|"
                      r"was bekomm|was kauft man|wat koop je|wat krijg je|"
                      r"qu'est-ce qu'on (peut )?ach[eè]te|que peut-on acheter|ce qu'on ach[eè]te",
}

# "Homes like #2 in Lisbon" — about a home on screen, somewhere else. Checked
# after the price and contact skills: "is #1's price in line with similar
# homes?" is a price check, not this.
_PATTERNS["similar-elsewhere"] = (
    r"\bsimilar\b|\b(homes?|flats?|apartments?|something|anything|one|ones)\s+like\b|like (this|that|it|#)|"
    r"parecid|semelhante|similares?\b|ähnlich|vergleichbar|vergelijkbar|zoals (#|deze|die)|"
    r"comme (celui|celle|ça|le n|la n)|semblable|pareil|"
    # two cards side by side ("Compare #1 and #4 feature by feature")
    r"feature by feature|side by side|caracter[ií]stica (a|por) caracter[ií]stica|point par point|"
    r"merkmal f[uü]r merkmal|kenmerk voor kenmerk")

# A budget refinement right after a comparison ("and up to 500k?", "what about
# 350 000?") stays a comparison rather than turning into a search.
_BUDGET_FOLLOW_UP = re.compile(r"\d|\bk\b|budget|instead|what about|and (at|for|up)|e (at[eé]|com|se)|"
                               r"y (hasta|con|si)|und (bis|mit)|et (à|jusqu|si)|en (tot|met|als)")


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
    paths = sorted(skills_dir.glob("*/SKILL.md"))
    if skills_dir == SKILLS_DIR:
        paths += sorted(LOCAL_SKILLS_DIR.glob("*/SKILL.md"))
    for p in paths:
        s = _parse(p)
        if s.name in TOOLS:
            out[s.name] = s
    return out


def select(message: str, has_results: bool, last_skill: str | None = None) -> str:
    """Pick a skill. Price/contact questions only make sense about a home already shown;
    an area question needs no results. Anything else searches homes."""
    low = message.lower()
    if re.search(_PATTERNS["compare-budget"], low):
        return "compare-budget"
    if (last_skill == "compare-budget" and _BUDGET_FOLLOW_UP.search(low)
            and not re.search(r"#\s*\d|\bn[º°o]\s*\d", low)):
        return "compare-budget"
    if has_results:
        for name in ("check-asking-price", "contact-agent", "similar-elsewhere"):
            if re.search(_PATTERNS[name], low):
                return name
    if re.search(_PATTERNS["compare-areas"], low) and not _looks_like_home_search(low):
        return "compare-areas"
    return "find-homes"


_HOME_WORDS = (r"\b(apartment|flat|house|villa|studio|penthouse|plot|land|t[0-9]|bed|bedroom|apartamento|"
               r"moradia|piso|casa|chalet|appartement|maison|wohnung|haus|woning|huis|for sale|to rent|"
               r"under \d|bis \d|até \d|hasta \d)")


def _looks_like_home_search(low: str) -> bool:
    """'2-bed flat near a metro station in Lisbon' is a home search, not an area question."""
    return re.search(_HOME_WORDS, low) is not None
