"""MRAT / closure interactions. Final closure is human-only (HEDIS nurse in MRAT); nothing here can set MRAT_CLOSED."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from trc_contracts import domain as d
from trc_contracts.common import Envelope, ExportFormat, ReviewStatusTarget, Disposition, Eligibility, RiskTier, TrcStatus, UploadStatus

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ..security import READ as S_READ, WRITE as S_WRITE
from ._common import READ, WRITE
from .types import IdemKey, MemberId, Reason


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_mrat_review_status", annotations=READ, tags={"trc", "read", "closure"})
    async def get_mrat_review_status(member_id: MemberId) -> Envelope[d.MratReviewStatus]:
        """MRAT review state for ONE member: awaiting HEDIS-nurse final closure?, assigned nurse pool, MRAT deep link ('View Details / MRAT
        Closure'), closed-at. Read-only."""
        return await run_tool(tc, tool="get_mrat_review_status", source="MRAT", op=Op.GET_MRAT_STATUS, path={"memberId": member_id},
                              model=d.MratReviewStatus, mapper=mappers.mrat, log_refs={"member": member_id})

    @mcp.tool(name="update_review_status", annotations=WRITE, tags={"trc", "write", "closure"})
    async def update_review_status(
        member_id: MemberId,
        target_status: Annotated[ReviewStatusTarget, Field(description="Only SOFT_CLOSED is allowed. Final MRAT closure is human-only.")],
        reason: Reason,
        idempotency_key: IdemKey = None,
    ) -> Envelope[d.ReviewStatusResult]:
        """WRITE. Soft-close ONE member's TRC task (VALIDATION_PASSED -> SOFT_CLOSED), which routes it to the MRAT queue for HEDIS-nurse
        final validation. On-prem rejects any other transition (PRECONDITION_FAILED). Cannot set MRAT_CLOSED. Requires explicit
        user confirmation (enforced by the agent)."""
        return await run_tool(tc, tool="update_review_status", source="TRC Event Processor / MRAT", op=Op.UPDATE_REVIEW_STATUS,
                              scopes=(S_READ, S_WRITE), body={"memberId": member_id, "targetStatus": target_status.value, "reason": reason},
                              write=True, idempotency_key=idempotency_key, model=d.ReviewStatusResult,
                              mapper=lambda r: mappers.review_result(r, target=target_status), log_refs={"member": member_id})

    @mcp.tool(name="request_worklist_export", annotations=WRITE, tags={"trc", "write", "export"})
    async def request_worklist_export(
        format: ExportFormat,
        trc_status: TrcStatus | None = None,
        risk_tier: RiskTier | None = None,
        provider_upload_status: UploadStatus | None = None,
        disposition: Disposition | None = None,
        eligibility: Eligibility | None = None,
        idempotency_key: IdemKey = None,
    ) -> Envelope[d.ExportJob]:
        """Create an on-prem export job for the filtered worklist (UI 'Export CSV/PDF'). The file is generated and hosted ON-PREM; the
        result is a short-lived download URL, never file bytes. Audit-logged on-prem."""
        filt = {k: v.value for k, v in {"trcStatus": trc_status, "riskTier": risk_tier, "uploadStatus": provider_upload_status,
                                        "disposition": disposition, "eligibility": eligibility}.items() if v is not None}
        return await run_tool(tc, tool="request_worklist_export", source="TRC Event Processor / GWDP", op=Op.CREATE_EXPORT,
                              scopes=(S_READ, S_WRITE), body={"format": format.value, "filters": filt}, write=True,
                              idempotency_key=idempotency_key, model=d.ExportJob, mapper=mappers.export_job)
