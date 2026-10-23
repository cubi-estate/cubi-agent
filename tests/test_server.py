import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent import server  # noqa: E402


class FakeAgent:
    def __init__(self):
        self.filter = None
        self.turns = 0

    def turn(self, text):
        self.turns += 1
        if text == "boom":
            raise RuntimeError("upstream down")
        yield {"type": "action", "text": "Searching listings (structured filter)"}
        yield {"type": "answer", "text": f"turn {self.turns}", "skill": "find-homes", "lang": "en", "latency_s": 0.1,
               "listings": [{"n": 1, "id": "t:1", "tags": ["Pool", "Elevator", "Pool"], "url": "https://cubi.estate/r/t%3A1"}],
               "guards": {}, "stats": {}, "timings": [("secret stage", 1.0)]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "Agent", FakeAgent)
    monkeypatch.setattr(server, "sessions", server.Sessions())
    monkeypatch.setattr(server, "limits", server.Limits())
    return TestClient(server.app)


def _events(r):
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def test_turn_streams_session_action_answer_and_keeps_the_session(client):
    ev = _events(client.post("/api/chat", json={"message": "flat in Porto"}))
    assert [e["type"] for e in ev] == ["session", "action", "answer"]
    sid = ev[0]["id"]
    assert ev[2]["listings"][0]["tags"] == ["Pool", "Elevator"]  # de-duplicated
    assert "timings" not in ev[2] and "guards" not in ev[2]  # internals stay server-side
    ev2 = _events(client.post("/api/chat", json={"message": "again", "session_id": sid}))
    assert ev2[0]["id"] == sid and ev2[-1]["text"] == "turn 2"


def test_upstream_failure_is_a_friendly_error(client):
    ev = _events(client.post("/api/chat", json={"message": "boom"}))
    assert ev[-1] == {"type": "error", "code": "upstream", "text": server.ERRORS["upstream"]}


def test_limits(client, monkeypatch):
    monkeypatch.setattr(server, "IP_TURNS_PER_MIN", 2)
    for _ in range(2):
        assert _events(client.post("/api/chat", json={"message": "hi"}))[-1]["type"] == "answer"
    assert _events(client.post("/api/chat", json={"message": "hi"}))[-1]["code"] == "rate_minute"
    long = _events(client.post("/api/chat", json={"message": "x" * 501}))
    assert long[-1]["code"] == "too_long"


def test_demo_budget(client, monkeypatch):
    monkeypatch.setattr(server, "DEMO_TURNS_PER_DAY", 0)
    assert _events(client.post("/api/chat", json={"message": "hi"}))[-1]["code"] == "demo_budget"


def test_no_message_text_in_logs(client, caplog):
    caplog.set_level("INFO", logger="cubi_agent")
    client.post("/api/chat", json={"message": "my secret street 12"})
    assert caplog.records and not any("secret" in r.getMessage() for r in caplog.records)


def test_page_and_health(client):
    assert "Cubi Agent" in client.get("/").text
    assert client.get("/api/health").json()["ok"] is True


def test_limits_forget_an_address_a_minute_after_its_last_turn(monkeypatch):
    lim = server.Limits()
    t = [1000.0]
    monkeypatch.setattr(server.time, "time", lambda: t[0])
    assert lim.check("203.0.113.7") is None
    t[0] += 61
    assert lim.check("198.51.100.2") is None
    assert "203.0.113.7" not in lim._minute and "198.51.100.2" in lim._minute
