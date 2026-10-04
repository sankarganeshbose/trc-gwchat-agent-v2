"""FastMCP server entrypoint (deployed on AgentCore Runtime with protocol=MCP, registered as an AgentCore Gateway target).

AgentCore Runtime MCP contract: stateless streamable-HTTP on 0.0.0.0:8000 at /mcp.
"""
from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from .clients.base import OnPremClient
from .clients.http import HttpOnPremClient
from .clients.stub import StubOnPremClient
from .config import Settings, get_settings
from .deps import ToolContext
from .logging import configure_logging, get_logger
from .security import ALL_SCOPES, Principal, principal_from_headers
from .tools import register_all

INSTRUCTIONS = (
    "GuideWell TRC (Transitions of Care) integration tools. Every tool returns an Envelope {ok, data, error, meta}. "
    "These tools are deterministic gateways to on-prem systems; they never infer or fabricate data. "
    "Tools tagged 'write' change enterprise state and must only be called after explicit user confirmation."
)


def build_client(settings: Settings) -> OnPremClient:
    return StubOnPremClient(settings) if settings.backend == "stub" else HttpOnPremClient(settings)


def _resolver(settings: Settings):
    def resolve() -> Principal:
        try:
            headers = get_http_headers(include_all=True)
        except RuntimeError:  # no HTTP request (in-memory transport in tests / stdio)
            headers = {}
        if not headers and not settings.require_auth:
            return Principal(user_id="dev-user", scopes=ALL_SCOPES)
        return principal_from_headers(headers, settings)
    return resolve


def build_server(settings: Settings | None = None, client: OnPremClient | None = None) -> FastMCP:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    tc = ToolContext(client=client or build_client(settings), settings=settings, principal_resolver=_resolver(settings))
    mcp = FastMCP(name="trc-mcp", instructions=INSTRUCTIONS)
    register_all(mcp, tc)
    mcp._trc_ctx = tc  # type: ignore[attr-defined]  # exposed for tests / graceful shutdown
    get_logger().info("server_built", backend=settings.backend, writes=settings.write_tools_enabled)
    return mcp


def main() -> None:
    mcp = build_server()
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp", stateless_http=True)


if __name__ == "__main__":
    main()
