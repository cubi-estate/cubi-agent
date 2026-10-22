"""Posts on X in the home-news turn: on demand, capped, filtered, cited, never stored."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import config, tavily_tool, x_tool  # noqa: E402

BODY = {"data": [
    {"id": "1", "author_id": "a", "text": "Rents in Lisbon up again, my landlord wants 20% more", "created_at": "2026-10-21T09:00:00Z"},
    {"id": "2", "author_id": "b", "text": "Stunning T2 for sale in Lisbon, DM me", "created_at": "2026-10-21T10:00:00Z"},
    {"id": "3", "author_id": "c", "text": "Lisbon housing protest tomorrow at 3pm", "created_at": "2026-10-20T10:00:00Z"},
    {"id": "4", "author_id": "d", "text": "Lisbon housing market update", "created_at": "2026-10-20T11:00:00Z"}],
    "includes": {"users": [{"id": "a", "username": "ana_l", "name": "Ana"},
                           {"id": "b", "username": "joao", "name": "João"},
                           {"id": "c", "username": "bairro_news", "name": "Bairro"},
                           {"id": "d", "username": "lisbonrealty", "name": "Lisbon Realty"}]}}


class _Http:
    def __init__(self, status=200, body=BODY):
        self.status, self.body, self.calls = status, body, []

    def get(self, url, params=None, headers=None):
        self.calls.append(params)
        return type("R", (), {"status_code": self.status, "json": lambda s: self.body,
                              "raise_for_status": lambda s: None})()


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(config, "X_BEARER_TOKEN", "test")
    monkeypatch.delenv("CUBI_OFFLINE", raising=False)
    monkeypatch.setattr(x_tool, "BUDGET", x_tool._Budget())


def test_query_has_both_names_and_no_retweets():
    q = x_tool.query_for("Lisboa")
    assert q.startswith("(Lisboa OR Lisbon) (housing OR rent") and "-is:retweet" in q and len(q) <= 512


def test_ads_and_agencies_dropped_rest_cited_as_posts():
    http = _Http()
    text, st = x_tool.recent_posts("Lisboa, Portugal", http=http, first_id=1)
    assert [p["id"] for p in st["posts"]] == ["1", "3"]
    assert st["sources"]["X1"]["url"] == "https://x.com/ana_l/status/1" and st["returned"] == 4
    assert "[X1] 2026-10-21" in text and "not reporting" in text and "ana_l" not in text
    assert http.calls[0]["max_results"] == 10


def test_daily_cap_stops_calls(monkeypatch):
    monkeypatch.setenv("X_DAILY_POST_CAP", "15")
    http = _Http()
    x_tool.recent_posts("Lisboa", http=http)
    with pytest.raises(x_tool.XError, match="budget"):
        x_tool.recent_posts("Porto", http=http)
    assert len(http.calls) == 1


def test_no_key_is_disabled(monkeypatch):
    monkeypatch.setattr(config, "X_BEARER_TOKEN", "")
    assert not x_tool.enabled()
    with pytest.raises(x_tool.XError):
        x_tool.recent_posts("Lisboa", http=_Http())


def test_credit_used_up_is_an_error():
    with pytest.raises(x_tool.XError, match="credit"):
        x_tool.recent_posts("Lisboa", http=_Http(status=402))


def test_x_citations_are_linked():
    sources = {"S1": {"url": "https://news.example/1", "title": "News", "date": ""},
               "X1": {"url": "https://x.com/ana_l/status/1", "title": "Ana (@ana_l) on X", "date": "2026-10-21"}}
    out, n = tavily_tool.link_citations("A march was held [S1]; posts on X mention rising rents [X1].", sources)
    assert n == 2 and "[X1](https://x.com/ana_l/status/1)" in out and "Ana (@ana_l) on X" in out
