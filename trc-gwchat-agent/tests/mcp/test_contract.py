from __future__ import annotations


from trc_agent.policy import ALLOWED_MCP_TOOLS, COMPUTE_TOOLS, READ_TOOLS, WRITE_TOOLS


async def test_tool_inventory_matches_agent_policy(mcp_client):
    tools = await mcp_client.list_tools()
    names = {t.name for t in tools}
    assert len(names) == 29
    assert names == ALLOWED_MCP_TOOLS, "agent allow-list and MCP server drifted"


async def test_every_tool_has_output_schema_and_hints(mcp_client):
    for t in await mcp_client.list_tools():
        assert t.outputSchema, f"{t.name} lacks an output schema"
        assert t.annotations is not None
        if t.name in READ_TOOLS:
            assert t.annotations.readOnlyHint is True
        if t.name in WRITE_TOOLS:
            assert t.annotations.readOnlyHint is False and "write" in t.meta["fastmcp"]["tags"]
        assert t.description and len(t.description) > 40


async def test_mrat_closed_is_not_a_legal_target(mcp_client):
    tool = next(t for t in await mcp_client.list_tools() if t.name == "update_review_status")
    enum = tool.inputSchema["properties"]["target_status"]["enum"]
    assert enum == ["SOFT_CLOSED"]


async def test_write_tools_are_classified(mcp_client):
    by = {t.name: t for t in await mcp_client.list_tools()}
    for n in WRITE_TOOLS:
        assert by[n].annotations.readOnlyHint is False
    for n in READ_TOOLS:
        assert by[n].annotations.readOnlyHint is True
    for n in COMPUTE_TOOLS:
        assert by[n].annotations.readOnlyHint is False and by[n].annotations.idempotentHint is True
