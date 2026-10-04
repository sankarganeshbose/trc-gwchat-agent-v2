from fastmcp import FastMCP

from ..deps import ToolContext
from . import closure, cohort, discharge, member, notification, provider, records, validation

MODULES = (cohort, member, discharge, provider, notification, validation, records, closure)


def register_all(mcp: FastMCP, tc: ToolContext) -> None:
    for m in MODULES:
        m.register(mcp, tc)
