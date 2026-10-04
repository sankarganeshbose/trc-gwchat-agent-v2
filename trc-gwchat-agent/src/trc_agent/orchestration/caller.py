"""ToolCaller: the single abstraction through which the agent code invokes MCP tools programmatically (playbooks, confirmed actions).

Production implementation talks MCP to AgentCore Gateway via Strands' MCPClient. Tests use an in-process FastMCP client.
Either way the agent never touches on-prem APIs.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from typing import Any, Protocol

from ..config import AgentSettings
from ..logging import get_logger
from ..policy import COMPUTE_TOOLS, READ_TOOLS, canonical
from ..services.ledger import failure_envelope, parse_tool_result

log = get_logger("trc_agent.caller")
RETRYABLE = {"UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE", "RATE_LIMITED"}


class ToolCaller(Protocol):
    async def call(self, tool: str, args: dict[str, Any]) -> dict:
        """Return an Envelope dict (never raises for tool-level failures)."""
        ...


class StrandsMcpToolCaller:
    """Calls tools on an already-started Strands MCPClient pointed at the AgentCore Gateway."""

    def __init__(self, client, tool_names: dict[str, str], timeout_s: float, write_timeout_s: float):
        self._client, self._names, self._t, self._wt = client, tool_names, timeout_s, write_timeout_s

    async def call(self, tool: str, args: dict[str, Any]) -> dict:
        actual = self._names.get(tool)
        if not actual:
            return failure_envelope("NOT_FOUND", f"Tool '{tool}' is not exposed by the gateway.")
        timeout = self._t if (tool in READ_TOOLS or tool in COMPUTE_TOOLS) else self._wt
        try:
            res = await asyncio.wait_for(self._client.call_tool_async(uuid.uuid4().hex, actual, args), timeout=timeout)
            return parse_tool_result(res)
        except asyncio.TimeoutError:
            return failure_envelope("UPSTREAM_TIMEOUT", "The enterprise service did not respond in time.", retryable=True)
        except Exception as exc:  # noqa: BLE001  transport/gateway failure
            log.warning("gateway_call_failed", tool=tool, error_type=type(exc).__name__)
            return failure_envelope("UPSTREAM_UNAVAILABLE", "Could not reach the tool gateway.", retryable=True)


class ResilientCaller:
    """Bounded retries with exponential backoff + jitter. Reads/compute: always safe. Writes: only when an idempotency key is present."""

    def __init__(self, inner: ToolCaller, settings: AgentSettings, *, sleep=asyncio.sleep):
        self._inner, self._s, self._sleep = inner, settings, sleep

    async def call(self, tool: str, args: dict[str, Any]) -> dict:
        tool = canonical(tool)
        safe = tool in READ_TOOLS or tool in COMPUTE_TOOLS or bool(args.get("idempotency_key"))
        attempts = 1 + (self._s.tool_retries if safe else 0)
        env: dict = failure_envelope("INTERNAL", "No attempt made.")
        for i in range(attempts):
            env = await self._inner.call(tool, args)
            err = env.get("error") or {}
            if env.get("ok") or err.get("code") not in RETRYABLE:
                return env
            if i + 1 < attempts:
                await self._sleep(self._s.retry_backoff_s * (2**i) * (0.5 + random.random()))
        return env
