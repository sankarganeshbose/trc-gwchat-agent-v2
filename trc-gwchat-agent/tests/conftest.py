from __future__ import annotations

import pytest
import pytest_asyncio
from fastmcp import Client

from trc_mcp.clients.stub import StubOnPremClient
from trc_mcp.config import Settings
from trc_mcp.server import build_server


@pytest.fixture
def settings() -> Settings:
    return Settings(backend="stub", require_auth=False, write_tools_enabled=True, log_level="ERROR")


@pytest.fixture
def stub(settings) -> StubOnPremClient:
    return StubOnPremClient(settings)


@pytest.fixture
def mcp_server(settings, stub):
    return build_server(settings, client=stub)


@pytest_asyncio.fixture
async def mcp_client(mcp_server):
    async with Client(mcp_server) as c:
        yield c


async def call(client: Client, tool: str, **args) -> dict:
    """Call a tool and return the Envelope dict (structured content)."""
    res = await client.call_tool(tool, args, raise_on_error=False)
    if res.is_error:
        return {"ok": False, "mcp_error": True, "text": res.content[0].text if res.content else ""}
    return res.structured_content


@pytest_asyncio.fixture
async def inproc(mcp_client):
    from tests.agent.helpers import InProcessCaller
    return InProcessCaller(mcp_client)
