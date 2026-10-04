from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastmcp import Client

from trc_agent.config import AgentSettings
from trc_agent.orchestration.gateway import GatewaySession
from trc_agent.services.confirmation import TicketSigner


class InProcessCaller:
    """ToolCaller bound to an in-memory FastMCP client (same contract path as the Gateway, minus the network)."""

    def __init__(self, client: Client):
        self.client = client
        self.log: list[tuple[str, dict]] = []

    async def call(self, tool: str, args: dict[str, Any]) -> dict:
        self.log.append((tool, args))
        res = await self.client.call_tool(tool, args, raise_on_error=False)
        if res.is_error:
            return {"ok": False, "data": None, "error": {"code": "INVALID_ARGUMENT", "message": "rejected", "retryable": False}, "meta": {}}
        return res.structured_content


class FakeConnector:
    def __init__(self, caller, agent_tools=None):
        self.caller, self.agent_tools = caller, agent_tools or []

    @asynccontextmanager
    async def open(self, inbound_authorization=None, correlation_id=None):
        yield GatewaySession(agent_tools=self.agent_tools, caller=self.caller)


def agent_settings(**kw) -> AgentSettings:
    base = dict(gateway_auth="none", write_actions_enabled=True, ticket_secret="unit-test-secret", retry_backoff_s=0.0, log_level="ERROR")
    base.update(kw)
    return AgentSettings(**base)


def signer(s: AgentSettings | None = None) -> TicketSigner:
    s = s or agent_settings()
    return TicketSigner(s.ticket_secret, s.ticket_ttl_s)
