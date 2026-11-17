"""Nebius Token Factory client (OpenAI-compatible API) with a role → model map."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import httpx
from openai import APITimeoutError, OpenAI

from . import config

log = logging.getLogger("cubi_agent.llm")

# The SDK's timeout bounds each phase (connect, write, each read) separately, so a
# call can run past it: on Nov 17 04:46 one call took 25.6 s under timeout=20.
# The wall clock is enforced here instead: each attempt runs on a worker thread
# and is abandoned at the deadline (its socket still closes on the SDK's own
# timeout), then the one retry runs.
_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="llm")


class _Completions:
    def __init__(self, raw: OpenAI, deadline: float, attempts: int):
        self._raw, self._deadline, self._attempts = raw, deadline, attempts

    def create(self, **kw):
        for attempt in range(1, self._attempts + 1):
            fut = _POOL.submit(self._raw.chat.completions.create, **kw)
            try:
                return fut.result(timeout=self._deadline)
            except FutureTimeout:
                fut.cancel()
                log.warning("model call over %.0f s, abandoned (attempt %d of %d)",
                            self._deadline, attempt, self._attempts)
            except APITimeoutError:
                log.warning("model call timed out in the SDK (attempt %d of %d)", attempt, self._attempts)
        raise APITimeoutError(request=httpx.Request("POST", str(self._raw.base_url) + "chat/completions"))


class _Chat:
    def __init__(self, completions: _Completions):
        self.completions = completions


class Client:
    """`chat.completions.create` with a wall-clock deadline per attempt and one retry."""

    def __init__(self, raw: OpenAI, deadline: float, attempts: int = 2):
        self.raw = raw
        self.timeout = deadline
        self.max_retries = attempts - 1
        self.chat = _Chat(_Completions(raw, deadline, attempts))


def client(timeout: float | None = None) -> Client:
    """One retry, and each attempt bounded end to end by `config.LLM_TIMEOUT_S` (20 s)."""
    if not config.NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not set (see .env.example)")
    deadline = config.LLM_TIMEOUT_S if timeout is None else timeout
    raw = OpenAI(
        base_url=config.TOKEN_FACTORY_BASE_URL,
        api_key=config.NEBIUS_API_KEY,
        timeout=deadline,
        max_retries=0,  # the retry is Client's, so it too gets a fresh deadline
    )
    return Client(raw, deadline)


def model(role: str) -> str:
    return config.MODELS[role]


# Nemotron 3 models reason by default. For structured extraction that is harmful:
# Nano spends its whole token budget thinking and returns nothing, and Super's
# reasoning leaks into schema-constrained fields (day-1 probe, 2026-10-13).
# Thinking off: 6/6 valid on both, ~1 s instead of 3-9 s.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
