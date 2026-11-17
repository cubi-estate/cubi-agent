"""The Token Factory client bounds each call (stalls of 15-60 s, Nov 3-16)."""
import importlib

from agent import config, llm


def test_default_deadline_is_20s_with_one_retry(monkeypatch):
    monkeypatch.setattr(config, "NEBIUS_API_KEY", "test")
    cli = llm.client()
    assert cli.timeout == 20.0
    assert cli.max_retries == 1


def test_explicit_timeout_wins(monkeypatch):
    monkeypatch.setattr(config, "NEBIUS_API_KEY", "test")
    assert llm.client(timeout=5.0).timeout == 5.0


def test_env_sets_the_deadline(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_S", "12.5")
    try:
        importlib.reload(config)
        assert config.LLM_TIMEOUT_S == 12.5
    finally:
        monkeypatch.delenv("LLM_TIMEOUT_S")
        importlib.reload(config)
    assert config.LLM_TIMEOUT_S == 20.0


class _SlowThenFast:
    """A raw client whose first call hangs and whose second answers at once."""

    def __init__(self, hang: float):
        self.hang, self.calls = hang, 0
        self.base_url = "http://test/v1/"
        self.chat = self
        self.completions = self

    def create(self, **kw):
        import time
        self.calls += 1
        if self.calls == 1:
            time.sleep(self.hang)
        return "answer"


def test_wall_clock_deadline_abandons_a_hung_call_and_retries():
    import time
    raw = _SlowThenFast(hang=2.0)
    cli = llm.Client(raw, deadline=0.3)
    t = time.monotonic()
    assert cli.chat.completions.create(model="m", messages=[]) == "answer"
    assert raw.calls == 2
    assert time.monotonic() - t < 1.0


def test_two_hung_attempts_raise_timeout():
    import time
    import pytest
    from openai import APITimeoutError

    class _Hang(_SlowThenFast):
        def create(self, **kw):
            self.calls += 1
            time.sleep(1.5)

    raw = _Hang(0)
    cli = llm.Client(raw, deadline=0.2)
    t = time.monotonic()
    with pytest.raises(APITimeoutError):
        cli.chat.completions.create(model="m", messages=[])
    assert raw.calls == 2
    assert time.monotonic() - t < 1.0
