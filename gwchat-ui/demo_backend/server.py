"""Local stand-in for the AgentCore Runtime *HTTP* contract, for demos without AWS.

    python -m demo_backend.server          # agent on :8080 (POST /invocations, GET /ping), MCP server on :8000/mcp

What is REAL: the Strands agent service (hooks, allow-list, confirmation tickets, ledger, blocks, grounding), the MCP client, and the FastMCP
server over streamable HTTP (the same server that is registered behind AgentCore Gateway). What is STAND-IN: (1) the LLM (keyword router),
(2) the AgentCore Gateway hop (agent calls the MCP server directly), (3) the on-prem API (in-memory stub seeded from the prototype's members).

The response is the normal GWChatResponse plus a `_demo` object (on-prem route timings) that a real agent would NOT return; the UI uses it
only to draw the on-prem hop.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from collections import defaultdict

import uvicorn
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from trc_agent.agent import TrcAgentService
from trc_agent.config import AgentSettings
from trc_agent.models.schemas import GWChatRequest
from trc_agent.orchestration.gateway import StrandsGatewayConnector
from trc_mcp.clients.base import DEFAULT_ROUTES
from trc_mcp.clients.stub import StubOnPremClient
from trc_mcp.config import Settings
from trc_mcp.server import build_server

from .router_model import DemoRouterModel

EVENTS: dict[str, list[dict]] = defaultdict(list)  # correlation id -> on-prem calls
T0 = time.monotonic()


class TimedStub(StubOnPremClient):
    """Stub on-prem API that adds a small latency and records the on-prem route each tool hit (for the flow diagram)."""

    LATENCY_S = float(os.getenv("DEMO_ONPREM_LATENCY_MS", "60")) / 1000

    async def call(self, op, *, ctx, path=None, query=None, body=None):
        start = time.monotonic()
        await asyncio.sleep(self.LATENCY_S)
        status = "ok"
        try:
            return await super().call(op, ctx=ctx, path=path, query=query, body=body)
        except Exception:
            status = "error"
            raise
        finally:
            method, tmpl = DEFAULT_ROUTES[op]
            route = tmpl.format(**path) if path else tmpl
            EVENTS[ctx.request_id].append({"tool": ctx.tool, "method": method, "route": route, "status": status,
                                           "ms": int((time.monotonic() - start) * 1000), "system": "stub on-prem API"})


def _wait_port(port: int, tries: int = 100) -> None:
    for _ in range(tries):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"MCP server did not start on :{port}")


def start_mcp(port: int):
    """Start the FastMCP server in a thread; returns (settings, stub) so the demo can reset the in-memory on-prem state."""
    settings = Settings(backend="stub", require_auth=False, write_tools_enabled=True, log_level="WARNING")
    stub = TimedStub(settings)
    server = build_server(settings, client=stub)
    threading.Thread(target=lambda: server.run(transport="http", host="127.0.0.1", port=port, path="/mcp", stateless_http=True, show_banner=False),
                     daemon=True, name="fastmcp").start()
    _wait_port(port)
    return settings, stub


def build_app(mcp_port: int | None = None) -> Starlette:
    mcp_port = mcp_port or int(os.getenv("DEMO_MCP_PORT", "8000"))
    mcp_settings, stub = start_mcp(mcp_port)
    s = AgentSettings(gateway_url=f"http://127.0.0.1:{mcp_port}/mcp", gateway_auth="none", write_actions_enabled=True,
                      ticket_secret=os.getenv("DEMO_TICKET_SECRET", "demo-only-secret-not-for-production-use"),
                      retry_backoff_s=0.0, log_level="WARNING")
    service = TrcAgentService(s, StrandsGatewayConnector(s), model_factory=lambda _s: DemoRouterModel())

    async def ping(_: Request) -> JSONResponse:
        return JSONResponse({"status": "Healthy", "mode": "demo", "mcp": f"http://127.0.0.1:{mcp_port}/mcp"})

    async def reset(_: Request) -> JSONResponse:
        """Demo only: restore the stub on-prem data (soft-closes, resends etc. are in-memory)."""
        stub.__init__(mcp_settings)  # type: ignore[misc]
        EVENTS.clear()
        return JSONResponse({"status": "reset"})

    async def invocations(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            payload.setdefault("session_id", request.headers.get("x-amzn-bedrock-agentcore-runtime-session-id", ""))
            req = GWChatRequest.model_validate(payload)
        except (ValidationError, json.JSONDecodeError, TypeError) as exc:
            return JSONResponse({"error": "INVALID_REQUEST", "detail": str(exc)[:500]}, status_code=422)
        t = time.monotonic()
        resp = await service.handle(req, inbound_authorization=request.headers.get("authorization"))
        out = resp.model_dump(mode="json")
        out["_demo"] = {"onprem_calls": EVENTS.pop(req.request_id, []), "agent_ms": int((time.monotonic() - t) * 1000),
                        "llm": "keyword router (demo stand-in for Bedrock)", "gateway": "bypassed in demo (agent → MCP direct)"}
        return JSONResponse(out)

    return Starlette(routes=[Route("/ping", ping), Route("/demo/reset", reset, methods=["POST"]), Route("/invocations", invocations, methods=["POST"])])


def main() -> None:
    port = int(os.getenv("DEMO_PORT", "8080"))
    print(f"Demo agent: http://localhost:{port}/invocations   MCP server: http://localhost:{os.getenv('DEMO_MCP_PORT', '8000')}/mcp")
    uvicorn.run(build_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
