"""Cohort-level reads: dashboard KPIs, metric breakdowns, worklist and closure board."""
from __future__ import annotations

from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import Field

from trc_contracts import domain as d
from trc_contracts.common import (
    Disposition, Eligibility, Envelope, LineOfBusiness, MetricDimension, RiskTier, TrcStatus, UploadStatus,
)

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ._common import READ
from .types import IsoDate

SORTS = {"risk_score_desc": "riskScore:desc", "discharge_date_desc": "dischargeDate:desc", "followup_due_asc": "followupDue:asc"}


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_trc_summary", annotations=READ, tags={"trc", "read", "cohort"})
    async def get_trc_summary() -> Envelope[d.TrcSummary]:
        """TRC dashboard snapshot for the measurement period: discharges identified, provider-notified / validation-passed /
        soft-closed counts and rates, members with no Provider Vista upload by day 3 (and how many are HIGH risk),
        awaiting-MRAT count, closure rate vs prior quarter and plan target, and risk-tier distribution.
        Use for 'how are we doing on TRC' / KPI questions. Not for member-level detail (use get_trc_worklist)."""
        return await run_tool(tc, tool="get_trc_summary", source="TRC Event Processor / GWDP", op=Op.GET_SUMMARY,
                              model=d.TrcSummary, mapper=mappers.summary)

    @mcp.tool(name="get_trc_metric_breakdown", annotations=READ, tags={"trc", "read", "cohort"})
    async def get_trc_metric_breakdown(
        dimension: Annotated[MetricDimension, Field(description="COMPONENT=measure component compliance, FACILITY=open-gap rate by facility, "
                                                                 "DISPOSITION=discharge disposition mix, TREND=trailing-12-month closure rate")],
    ) -> Envelope[d.MetricBreakdown]:
        """One dashboard breakdown (chart/table data) for the TRC measure. Choose exactly one dimension per call."""
        return await run_tool(tc, tool="get_trc_metric_breakdown", source="TRC Event Processor / GWDP", op=Op.GET_METRICS,
                              path={"dimension": dimension.value}, model=d.MetricBreakdown, mapper=mappers.metrics)

    @mcp.tool(name="get_trc_worklist", annotations=READ, tags={"trc", "read", "cohort"})
    async def get_trc_worklist(
        query: Annotated[str | None, Field(max_length=60, description="Member name, HCCID or MRN fragment")] = None,
        eligibility: Eligibility | None = None,
        disposition: Disposition | None = None,
        trc_status: TrcStatus | None = None,
        provider_upload_status: UploadStatus | None = None,
        risk_tier: RiskTier | None = None,
        facility: Annotated[str | None, Field(max_length=120)] = None,
        line_of_business: LineOfBusiness | None = None,
        discharge_from: IsoDate | None = None,
        discharge_to: IsoDate | None = None,
        lookback_days: Annotated[int | None, Field(ge=1, le=365, description="Discharged within the last N days")] = None,
        past_day3_no_upload_only: Annotated[bool, Field(description="Only members past day 3 post-discharge with NO Provider Vista upload")] = False,
        sort_by: Literal["risk_score_desc", "discharge_date_desc", "followup_due_asc"] = "risk_score_desc",
        limit: Annotated[int, Field(ge=1, le=50)] = 25,
        cursor: Annotated[str | None, Field(max_length=64, description="Opaque cursor from a previous page")] = None,
    ) -> Envelope[d.WorklistPage]:
        """TRC worklist: one row per TRC discharge with measure status, risk, provider-notification status and Provider Vista
        upload status. Supports every filter in the GWChat worklist UI. Use for 'show members discharged in the last N days where the provider has not
        uploaded documents by day 3 ranked by risk' (lookback_days=N, past_day3_no_upload_only=true, sort_by=risk_score_desc),
        and for 'list all members on the TRC worklist'. Returns a page; use `total_matching` vs `returned` to report truncation."""
        limit = min(limit, tc.settings.max_page_size)
        applied = {k: (v.value if hasattr(v, "value") else v) for k, v in {
            "query": query, "eligibility": eligibility, "disposition": disposition, "trc_status": trc_status,
            "provider_upload_status": provider_upload_status, "risk_tier": risk_tier, "facility": facility,
            "line_of_business": line_of_business, "discharge_from": discharge_from, "discharge_to": discharge_to,
            "lookback_days": lookback_days, "past_day3_no_upload_only": past_day3_no_upload_only or None, "limit": limit}.items()
            if v is not None}
        q = {"q": query, "eligibility": eligibility, "disposition": disposition, "trcStatus": trc_status,
             "uploadStatus": provider_upload_status, "riskTier": risk_tier, "facility": facility, "lineOfBusiness": line_of_business,
             "dischargeFrom": discharge_from, "dischargeTo": discharge_to, "lookbackDays": lookback_days,
             "pastDay3Only": True if past_day3_no_upload_only else None, "sort": SORTS[sort_by], "limit": limit, "cursor": cursor}
        q = {k: (v.value if hasattr(v, "value") else v) for k, v in q.items() if v is not None}
        return await run_tool(tc, tool="get_trc_worklist", source="TRC Event Processor / GWDP", op=Op.GET_WORKLIST, query=q,
                              model=d.WorklistPage, mapper=lambda r: mappers.worklist(r, sort=sort_by, filters=applied))

    @mcp.tool(name="get_closure_board", annotations=READ, tags={"trc", "read", "cohort"})
    async def get_closure_board() -> Envelope[d.ClosureBoard]:
        """Kanban view of measure status: Discharge Identified -> Provider Notified -> Validation Passed -> Soft Closed/MRAT,
        with member cards per column. Read-only; does not run validation (use validate_claims for that)."""
        return await run_tool(tc, tool="get_closure_board", source="TRC Event Processor / GWDP", op=Op.GET_CLOSURE_BOARD,
                              model=d.ClosureBoard, mapper=mappers.closure_board)
