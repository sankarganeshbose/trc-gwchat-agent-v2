"""Deterministic validation reads + claim validation run."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from trc_contracts import domain as d
from trc_contracts.common import Envelope

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ..security import READ as S_READ
from ._common import COMPUTE, READ
from .types import MemberId


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_validation_evidence", annotations=READ, tags={"trc", "read", "validation"})
    async def get_validation_evidence(member_id: MemberId) -> Envelope[d.ValidationEvidence]:
        """Validation evidence for ONE member: Provider Vista upload, claim match in the 3-day window, Care Navi task status and
        the evidence checklist (discharge summary, provider notification, provider records, claim match) with the rules-engine outcome.
        Does NOT re-run validation (use validate_claims)."""
        return await run_tool(tc, tool="get_validation_evidence", source="Provider Vista + Claims + Care Navi", op=Op.GET_VALIDATION,
                              path={"memberId": member_id}, model=d.ValidationEvidence, mapper=mappers.validation_evidence,
                              log_refs={"member": member_id})

    @mcp.tool(name="get_validation_summary", annotations=READ, tags={"trc", "read", "validation"})
    async def get_validation_summary() -> Envelope[d.ValidationSummary]:
        """Aggregate Deterministic Validation Agent metrics (tasks evaluated, % notified <=1 day, % records uploaded by day 3,
        % claims validated, % passed->soft closed, % failed, avg days to soft closure, awaiting MRAT)."""
        return await run_tool(tc, tool="get_validation_summary", source="Validation Agent / GWDP", op=Op.GET_VALIDATION_SUMMARY,
                              model=d.ValidationSummary, mapper=mappers.validation_summary)

    @mcp.tool(name="validate_claims", annotations=COMPUTE, tags={"trc", "compute", "validation"})
    async def validate_claims(
        member_ids: Annotated[list[MemberId] | None, Field(max_length=200, description="Members to validate. Omit to validate ALL open TRC Proxy Tasks.")] = None,
    ) -> Envelope[d.ValidationRun]:
        """Run the deterministic, rule-based validation (Provider Vista upload present + claim matched within the 3-day window + Care
        Navi task) and return a per-member outcome. Rules live on-prem; this tool never decides outcomes itself. It does NOT soft-close
        anything (see update_review_status). Idempotent. Used for 'run the validation agent' and 'Re-run validate_claims()'."""
        ids = list(dict.fromkeys(member_ids)) if member_ids else None
        body = {"memberIds": ids, "windowDays": 3, "persist": True}
        return await run_tool(tc, tool="validate_claims", source="Validation Agent / Claims", op=Op.RUN_CLAIM_VALIDATION,
                              scopes=(S_READ,), body=body, compute=True, model=d.ValidationRun, mapper=mappers.validation_run)
