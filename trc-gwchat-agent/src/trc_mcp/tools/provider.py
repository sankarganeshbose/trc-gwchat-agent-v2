"""Provider Directory reads."""
from __future__ import annotations

from fastmcp import FastMCP

from trc_contracts import domain as d
from trc_contracts.common import Envelope

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ._common import READ
from .types import ProviderId


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_provider_contacts", annotations=READ, tags={"trc", "read", "provider"})
    async def get_provider_contacts(provider_id: ProviderId) -> Envelope[d.ProviderContacts]:
        """Verified provider contact channels (fax / email / provider proxy task) from Provider Directory, with verification date and
        preferred channel. Values are masked. Use before resending an alert or to answer 'how will we reach Dr. X'."""
        return await run_tool(tc, tool="get_provider_contacts", source="Provider Directory", op=Op.GET_PROVIDER_CONTACTS,
                              path={"providerId": provider_id}, model=d.ProviderContacts, mapper=mappers.provider_contacts,
                              log_refs={"provider": provider_id})
