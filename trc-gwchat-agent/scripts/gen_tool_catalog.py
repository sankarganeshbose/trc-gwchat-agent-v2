"""Generate docs/TOOL_CATALOG.md from the LIVE FastMCP server (so the catalog can never drift from the code).

    python scripts/gen_tool_catalog.py > docs/TOOL_CATALOG.md
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastmcp import Client

from trc_mcp.clients.base import DEFAULT_ROUTES, Op
from trc_mcp.config import Settings
from trc_mcp.server import build_server

SRC = Path(__file__).resolve().parents[1] / "src/trc_mcp/tools"


def tool_ops() -> dict[str, tuple[str, str]]:
    """tool name -> (Op, source system) by reading the registration sites (decorator name + the run_tool(...) that follows)."""
    out: dict[str, tuple[str, str]] = {}
    for f in SRC.glob("*.py"):
        txt = f.read_text()
        for m in re.finditer(r'@mcp\.tool\(name="(\w+)".*?source="([^"]+)", op=Op\.(\w+)', txt, re.S):
            out[m.group(1)] = (m.group(3), m.group(2))
    return out


def klass(tags: list[str]) -> str:
    return "WRITE" if "write" in tags else "COMPUTE" if "compute" in tags else "READ"


async def main() -> None:
    ops = tool_ops()
    async with Client(build_server(Settings(require_auth=False, write_tools_enabled=True, log_level="ERROR"))) as c:
        tools = sorted(await c.list_tools(), key=lambda t: (klass(t.meta["fastmcp"]["tags"]) != "READ", t.name))
    print("# MCP tool catalog (generated)\n")
    print(f"{len(tools)} tools · Envelope `{{ok, data, error, meta}}` on every response · routes are PLACEHOLDERS (override via `TRC_MCP_ENDPOINT_OVERRIDES_JSON`).\n")
    print("| Tool | Class | Required inputs | Optional inputs | On-prem route (placeholder) | Source system | Idempotency |")
    print("|---|---|---|---|---|---|---|")
    for t in tools:
        props, req = t.inputSchema.get("properties", {}), set(t.inputSchema.get("required", []))
        op, src = ops[t.name]
        method, path = DEFAULT_ROUTES[Op(op)]
        k = klass(t.meta["fastmcp"]["tags"])
        idem = "ticket-derived key (agent) / auto key (server)" if k == "WRITE" else "idempotent run record" if k == "COMPUTE" else "n/a (GET)"
        print(f"| `{t.name}` | {k} | {', '.join(f'`{p}`' for p in props if p in req) or '—'} | {', '.join(f'`{p}`' for p in props if p not in req) or '—'} "
              f"| `{method} {path}` | {src} | {idem} |")
    print("\n## Per-tool descriptions (what the LLM sees)\n")
    for t in tools:
        print(f"### `{t.name}`\n\n{t.description.strip()}\n")


if __name__ == "__main__":
    asyncio.run(main())
