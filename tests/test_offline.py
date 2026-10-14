import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.mcp_client import MCPError, parse_rpc_body, to_openai_tool  # noqa: E402
from agent.schema import SearchFilter, strict_json_schema  # noqa: E402
from scripts.day1_probe import score  # noqa: E402


def test_parse_sse_and_json():
    sse = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    assert parse_rpc_body(sse, "text/event-stream")["result"] == {"ok": True}
    assert parse_rpc_body('{"jsonrpc":"2.0","id":1,"result":{}}', "application/json")["result"] == {}
    with pytest.raises(MCPError):
        parse_rpc_body("event: ping\n\n", "text/event-stream")


def test_strict_schema_requires_every_field():
    s = strict_json_schema()
    assert set(s["required"]) == set(s["properties"])
    assert s["additionalProperties"] is False


def _filter(**kw):
    base = dict(location=[], type=[], transaction_type="sale", min_price=None, max_price=None,
                min_bedrooms=None, max_bedrooms=None, min_living_area=None, has_parking=None,
                features=[], lang="en", needs_free_text_search=False)
    base.update(kw)
    return SearchFilter(**base)


def test_rent_sets_monthly_period_and_drops_empty_fields():
    args = _filter(location=["Lisboa"], transaction_type="rent", max_price=1500, lang="pt").to_filter_args()
    assert args["price_period"] == "month"
    assert args["location"] == ["Lisboa"]
    assert "type" not in args and "min_price" not in args


def test_score_aliases_and_accents():
    pred = _filter(location=["Málaga"], transaction_type="rent", max_price=1200.0).model_dump()
    hits, of, misses = score(pred, {"location": ["malaga"], "transaction_type": "rent", "max_price": 1200})
    assert (hits, of, misses) == (3, 3, [])
    hits, _, _ = score(_filter(location=["Lisbon"]).model_dump(), {"location": ["lisboa|lisbon"]})
    assert hits == 1


def test_fixture_tools_convert():
    tools = json.loads((ROOT / "fixtures" / "mcp_tools.json").read_text())
    converted = [to_openai_tool(t) for t in tools]
    names = {t["function"]["name"] for t in converted}
    assert {"filter_listings", "search_properties", "get_listing"} <= names


def test_in_band_error_detected():
    from agent.mcp_client import _in_band_error
    assert _in_band_error('{"is_error": true, "code": "search_incomplete"}')
    assert not _in_band_error("Showing 3 properties.")
    assert not _in_band_error('{"listings": []}')
