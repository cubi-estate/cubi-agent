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
