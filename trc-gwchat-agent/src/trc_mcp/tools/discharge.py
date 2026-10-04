"""Discharge-related reads."""
from __future__ import annotations

from fastmcp import FastMCP

from trc_contracts import domain as d
from trc_contracts.common import Envelope

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ._common import READ
from .types import MemberId


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_discharge_summary", annotations=READ, tags={"trc", "read", "discharge"})
    async def get_discharge_summary(member_id: MemberId) -> Envelope[d.DischargeSummary]:
        """Discharge diagnosis, disposition, discharging facility, source documents (ADT A03 + CCDA) and last-updated time for ONE member."""
        return await run_tool(tc, tool="get_discharge_summary", source="ADT / HIE + EIP", op=Op.GET_DISCHARGE, path={"memberId": member_id},
                              model=d.DischargeSummary, mapper=mappers.discharge,
                              log_refs={"member": member_id})

    @mcp.tool(name="get_discharge_medications", annotations=READ, tags={"trc", "read", "discharge"})
    async def get_discharge_medications(member_id: MemberId) -> Envelope[d.DischargeMedications]:
        """Discharge medication list (name, dose, frequency, indication) for ONE member. `on_file=false` means none on file
        — it does NOT mean the member has no medications. Supports medication-reconciliation review."""
        return await run_tool(tc, tool="get_discharge_medications", source="EIP / CCDA", op=Op.GET_DISCHARGE_MEDS, path={"memberId": member_id},
                              model=d.DischargeMedications, mapper=mappers.discharge_meds, log_refs={"member": member_id})

    @mcp.tool(name="get_followup_status", annotations=READ, tags={"trc", "read", "discharge"})
    async def get_followup_status(member_id: MemberId) -> Envelope[d.FollowupStatus]:
        """PCP follow-up timeframe for ONE member: due date, days until due (negative = overdue), overdue flag,
        discharge follow-up recommendations and whether a PCP visit is confirmed."""
        return await run_tool(tc, tool="get_followup_status", source="Care Navi / ADT", op=Op.GET_FOLLOWUP, path={"memberId": member_id},
                              model=d.FollowupStatus, mapper=mappers.followup, log_refs={"member": member_id})
