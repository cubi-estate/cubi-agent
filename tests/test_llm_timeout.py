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
