from __future__ import annotations

import socket
import threading
import time
from collections.abc import AsyncIterable

import pytest

from strands.models import Model

from trc_mcp.clients.stub import StubOnPremClient
from trc_mcp.config import Settings
from trc_mcp.server import build_server


class ScriptedModel(Model):
    """Deterministic stand-in for Bedrock: each model step is either tool calls (issued together => parallel) or final text."""

    def __init__(self, script: list[dict]):
        self.script, self.i = list(script), 0
        self.config: dict = {}

    def update_config(self, **model_config): self.config.update(model_config)

    def get_config(self): return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kw):  # pragma: no cover
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncIterable[dict]:
        step = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        yield {"messageStart": {"role": "assistant"}}
        if "tools" in step:
            for n, (name, args) in enumerate(step["tools"]):
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"tu{self.i}_{n}", "name": name}}}}
                import json
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}}
                yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": step["text"]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_mcp():
    """A real FastMCP server over streamable HTTP (what AgentCore Gateway would call), backed by the stub on-prem client."""
    settings = Settings(backend="stub", require_auth=False, write_tools_enabled=True, log_level="ERROR")
    stub = StubOnPremClient(settings)
    server = build_server(settings, client=stub)
    port = _free_port()
    t = threading.Thread(target=lambda: server.run(transport="http", host="127.0.0.1", port=port, path="/mcp", stateless_http=True, show_banner=False), daemon=True)
    t.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("MCP server did not start")
    return f"http://127.0.0.1:{port}/mcp", stub
