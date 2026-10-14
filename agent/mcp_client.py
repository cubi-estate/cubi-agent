"""A small client for Cubi Estate's public MCP connector (streamable HTTP).

The connector is stateless and read-only, so a request is one JSON-RPC POST.
Replies arrive either as JSON or as a server-sent-event stream carrying one
JSON-RPC message; both are handled here. Kept dependency-light on purpose so
the whole protocol path is readable in one file.
"""
from __future__ import annotations

import itertools
import json
from typing import Any

import httpx

from . import config

PROTOCOL_VERSION = "2025-06-18"


class MCPError(RuntimeError):
    pass


def parse_rpc_body(body: str, content_type: str) -> dict:
    """Return the JSON-RPC message from a JSON or SSE response body."""
    if "text/event-stream" not in (content_type or ""):
        return json.loads(body)
    data_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line.strip() and data_lines:
            break  # end of the first event
    if not data_lines:
        raise MCPError("empty event stream")
    return json.loads("\n".join(data_lines))


class CubiMCP:
    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 45.0):
        self.url = url or config.CUBI_MCP_URL
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": config.USER_AGENT,
        }
        token = config.CUBI_MCP_TOKEN if token is None else token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(headers=headers, timeout=timeout)
        self._ids = itertools.count(1)
        self._tools: list[dict] | None = None

    def _rpc(self, method: str, params: dict | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {}}
        r = self._http.post(self.url, json=payload)
        if r.status_code == 429:
            raise MCPError("Cubi connector rate limit reached; try again shortly")
        r.raise_for_status()
        msg = parse_rpc_body(r.text, r.headers.get("content-type", ""))
        if "error" in msg:
            raise MCPError(f"{method}: {msg['error'].get('message')}")
        return msg["result"]

    def initialize(self) -> dict:
        return self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "cubi-agent", "version": "0.1"},
            },
        )

    def list_tools(self) -> list[dict]:
        if self._tools is None:
            self._tools = self._rpc("tools/list")["tools"]
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Returns {"text": str, "is_error": bool, "structured": dict|None}."""
        res = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return {
            "text": text,
            "is_error": bool(res.get("isError")) or _in_band_error(text),
            "structured": res.get("structuredContent"),
        }

    def openai_tools(self, names: list[str] | None = None) -> list[dict]:
        """MCP tool schemas → OpenAI `tools` format, optionally scoped to `names`."""
        out = []
        for t in self.list_tools():
            if names is not None and t["name"] not in names:
                continue
            out.append(to_openai_tool(t))
        return out


def _in_band_error(text: str) -> bool:
    """The connector reports some failures (e.g. search_incomplete) as a JSON body
    with "is_error": true rather than via MCP's isError flag."""
    head = text.lstrip()
    if not head.startswith("{"):
        return False
    try:
        return bool(json.loads(head).get("is_error"))
    except (json.JSONDecodeError, AttributeError):
        return False


def to_openai_tool(t: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": (t.get("description") or "").strip()[:1024],
            "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
        },
    }
