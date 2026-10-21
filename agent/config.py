"""Runtime configuration, read from the environment (and an optional .env file)."""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path = _ROOT / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env wins. No dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
TOKEN_FACTORY_BASE_URL = os.environ.get(
    "TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"
)

# Role → model. Super is the default for everything until the eval gate
# promotes Nano (extraction) or Ultra (area-compare verdict).
MODELS = {
    "nano": os.environ.get("MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    "super": os.environ.get("MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
    "ultra": os.environ.get("MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b"),
    # Newer than the plan; probed as a candidate for the fast calls.
    "lightning": os.environ.get("MODEL_LIGHTNING", "nvidia/Nemotron-3_5-Lightning"),
}

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

CUBI_MCP_URL = os.environ.get("CUBI_MCP_URL", "https://mcp.cubi.estate/mcp")
CUBI_MCP_TOKEN = os.environ.get("CUBI_MCP_TOKEN", "")
# The build is in the User-Agent so Cubi's usage stats can tell the hosted demo
# (a commit sha, set by the Dockerfile) from local runs and evals ("build dev").
BUILD = os.environ.get("CUBI_AGENT_BUILD", "dev")[:12] or "dev"
USER_AGENT = os.environ.get("CUBI_AGENT_USER_AGENT",
                            f"cubi-agent/0.1 (build {BUILD}; +https://github.com/cubi-estate/cubi-agent)")
