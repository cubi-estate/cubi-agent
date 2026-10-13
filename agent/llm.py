"""Nebius Token Factory client (OpenAI-compatible API) with a role → model map."""
from __future__ import annotations

from openai import OpenAI

from . import config


def client(timeout: float = 60.0) -> OpenAI:
    if not config.NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not set (see .env.example)")
    return OpenAI(
        base_url=config.TOKEN_FACTORY_BASE_URL,
        api_key=config.NEBIUS_API_KEY,
        timeout=timeout,
        max_retries=1,
    )


def model(role: str) -> str:
    return config.MODELS[role]


# Nemotron 3 models reason by default. For structured extraction that is harmful:
# Nano spends its whole token budget thinking and returns nothing, and Super's
# reasoning leaks into schema-constrained fields (day-1 probe, 2026-10-13).
# Thinking off: 6/6 valid on both, ~1 s instead of 3-9 s.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
