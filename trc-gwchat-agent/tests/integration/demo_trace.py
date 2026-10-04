"""Executable walk-through: GWChat prompt -> Agent (Strands) -> MCP/HTTP -> FastMCP tool -> on-prem API (stub) -> back.

    python -m tests.integration.demo_trace

The LLM is replaced by a scripted model (so output is deterministic); everything else is the real code path.
"""
from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

from trc_agent.agent import TrcAgentService
from trc_agent.models.schemas import GWChatRequest
from trc_agent.orchestration.gateway import StrandsGatewayConnector
from tests.agent.helpers import agent_settings
from tests.integration.conftest import ScriptedModel
from trc_mcp.clients.base import DEFAULT_ROUTES
from trc_mcp.clients.stub import StubOnPremClient
from trc_mcp.config import Settings
from trc_mcp.server import build_server

T0 = time.monotonic()
EVENTS: list[tuple[float, float, str, str]] = []


class TimedStub(StubOnPremClient):
    async def call(self, op, *, ctx, path=None, query=None, body=None):
        s = time.monotonic()
        await asyncio.sleep(0.05)  # simulate on-prem latency so parallelism is visible
        try:
            return await super().call(op, ctx=ctx, path=path, query=query, body=body)
        finally:
            m, p = DEFAULT_ROUTES[op]
            EVENTS.append((s - T0, time.monotonic() - T0, ctx.tool, f"{m} {p.format(**{k: v for k, v in (path or {}).items()}) if path else p}"
                           + (f"?{json.dumps(dict(query), separators=(',', ':'))}" if query and m == 'GET' else "")))


def start_server():
    settings = Settings(require_auth=False, write_tools_enabled=True, log_level="ERROR")
    stub = TimedStub(settings)
    server = build_server(settings, client=stub)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    threading.Thread(target=lambda: server.run(transport="http", host="127.0.0.1", port=port, path="/mcp", stateless_http=True, show_banner=False), daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); break
        except OSError:
            time.sleep(0.1)
    return f"http://127.0.0.1:{port}/mcp", stub


async def scenario(title, url, script, message=None, confirmation=None, ctx=None):
    EVENTS.clear()
    s = agent_settings(gateway_url=url)
    svc = TrcAgentService(s, StrandsGatewayConnector(s), model_factory=lambda _s: ScriptedModel(script))
    req = GWChatRequest(session_id="sess-demo-0001", user_id="sankar", message=message, confirmation=confirmation, context=ctx or {})
    t = time.monotonic()
    r = await svc.handle(req)
    t = time.monotonic()
    print(f"\n{'═' * 100}\n{title}\n{'═' * 100}")
    print(f'GWChat → Agent          "{message or "<confirmation: " + confirmation["decision"] + ">"}"')
    for t0, t1, tool, route in sorted(EVENTS, key=lambda e: e[0]):
        print(f"  Gateway/MCP tools/call  {tool:<28} → FastMCP → on-prem {route[:70]:<70} [{t0 * 1000:6.0f}ms → {t1 * 1000:6.0f}ms]")
    print(f"Agent → GWChat          status={r.status.value} intent={r.intent} blocks={[b.type.value for b in r.blocks]} gaps={len(r.data_gaps)} pending={len(r.pending_actions)} warnings={r.warnings}")
    print(f'                        message="{r.message}"')
    return r


async def main():
    url, stub = start_server()
    await scenario("1) Single tool — 'Show me the TRC status for member HCC-4471829'", url,
                   [{"tools": [("get_member_trc_status", {"member_id": "HCC-4471829"})]}, {"text": "HCC-4471829 is at Provider Notified; the fax alert is PENDING and no Provider Vista upload is on file."}],
                   message="Show me the TRC status for member HCC-4471829")
    await scenario("2) Parallel fan-out + dependency — 'Open the TRC record for HCC-4471829'", url,
                   [{"tools": [("load_member_trc_record", {"member_id": "HCC-4471829"})]}, {"text": "Record loaded for HCC-4471829. Provider alert PENDING; no upload; HIGH risk."}],
                   message="Open the TRC record for Dorothy Simmons (HCC-4471829)")
    r = await scenario("3a) Write proposal — 'Resend the failed alert for HCC-2231087' (NOT executed)", url,
                       [{"tools": [("send_provider_notification", {"member_id": "HCC-2231087", "reason": "Resend failed fax alert"})]}, {"text": "The resend for HCC-2231087 is awaiting your confirmation."}],
                       message="Resend the failed provider alert for HCC-2231087")
    print("                        pending:", r.pending_actions[0].summary)
    await scenario("3b) User clicks Approve → deterministic execution (no LLM)", url, [{"text": "unused"}],
                   confirmation={"ticket": r.pending_actions[0].ticket, "decision": "approve"})
    await scenario("3c) Same Approve replayed (double-click) → server dedupes via ticket-derived idempotency key", url, [{"text": "unused"}],
                   confirmation={"ticket": r.pending_actions[0].ticket, "decision": "approve"})


if __name__ == "__main__":
    asyncio.run(main())
