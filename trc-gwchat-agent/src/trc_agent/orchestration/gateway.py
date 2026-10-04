"""AgentCore Gateway connection (MCP over streamable HTTP) built on Strands' MCPClient. Isolated so framework startup code never leaks into logic."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

import httpx
from strands.tools.mcp import MCPClient

from ..config import AgentSettings
from ..policy import ALLOWED_MCP_TOOLS, canonical
from .caller import StrandsMcpToolCaller


@dataclass
class GatewaySession:
    agent_tools: list[Any]  # Strands tool objects handed to the Agent (already allow-list filtered)
    caller: Any  # ToolCaller bound to the same MCP session


class GatewayConnector(Protocol):
    def open(self, inbound_authorization: str | None) -> "AsyncIterator[GatewaySession]": ...


class _ClientCredentials:
    def __init__(self, s: AgentSettings):
        self._s, self._tok, self._exp = s, None, 0.0

    async def header(self) -> str:
        if self._tok and time.monotonic() < self._exp - 60:
            return self._tok
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(self._s.token_url, data={"grant_type": "client_credentials", "client_id": self._s.client_id,
                                                      "client_secret": self._s.client_secret, **({"scope": self._s.scope} if self._s.scope else {})})
            r.raise_for_status()
            b = r.json()
        self._tok, self._exp = f"Bearer {b['access_token']}", time.monotonic() + float(b.get("expires_in", 300))
        return self._tok


class StrandsGatewayConnector:
    def __init__(self, settings: AgentSettings):
        self._s = settings
        self._cc = _ClientCredentials(settings) if settings.gateway_auth == "client_credentials" else None

    async def _auth_header(self, inbound: str | None) -> dict[str, str]:
        if self._s.gateway_auth == "propagate":
            if not inbound:
                raise PermissionError("No inbound Authorization header to propagate to the gateway.")
            return {"Authorization": inbound}
        if self._cc:
            return {"Authorization": await self._cc.header()}
        return {}

    @asynccontextmanager
    async def open(self, inbound_authorization: str | None, correlation_id: str | None = None) -> AsyncIterator[GatewaySession]:
        headers = await self._auth_header(inbound_authorization)
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        # Strands builds the streamable-HTTP transport itself when given url+headers (clean teardown on stop()).
        client = MCPClient(url=self._s.gateway_url, headers=headers, startup_timeout=int(self._s.gateway_connect_timeout_s))
        await asyncio.to_thread(client.start)
        try:
            tools = await asyncio.to_thread(client.list_tools_sync)
            allowed = [t for t in tools if canonical(t.tool_name) in ALLOWED_MCP_TOOLS]
            names = {canonical(t.tool_name): t.tool_name for t in allowed}
            caller = StrandsMcpToolCaller(client, names, self._s.tool_timeout_s, self._s.write_tool_timeout_s)
            yield GatewaySession(agent_tools=allowed, caller=caller)
        finally:
            await asyncio.to_thread(client.stop, None, None, None)
