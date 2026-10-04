"""Member-level reads (single member, keyed by HCCID) and the intervention log write."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from trc_contracts import domain as d
from trc_contracts.common import Envelope

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ..security import READ as S_READ, WRITE as S_WRITE
from ._common import READ, WRITE
from .types import IdemKey, MemberId


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_member_details", annotations=READ, tags={"trc", "read", "member"})
    async def get_member_details(member_id: MemberId) -> Envelope[d.MemberDetails]:
        """Demographics, admission (facility, type, dates), principal diagnosis, disposition, TRC eligibility (with exclusion reason,
        e.g. EXPIRED), current TRC status and PCP follow-up due date for ONE member."""
        return await run_tool(tc, tool="get_member_details", source="EDS-EIS / ADT", op=Op.GET_MEMBER, path={"memberId": member_id},
                              model=d.MemberDetails, mapper=mappers.member, log_refs={"member": member_id})

    @mcp.tool(name="get_member_trc_status", annotations=READ, tags={"trc", "read", "member"})
    async def get_member_trc_status(member_id: MemberId) -> Envelope[d.MemberTrcStatus]:
        """Current TRC measure status for ONE member as the 5-step tracker (Discharge Identified, Provider Notified, Validation Passed,
        Soft Closed, MRAT Final Closure) with each step's state (DONE / IN_PROGRESS / PENDING / FAILED) and evidence detail, plus
        eligibility (and exclusion reason). Use for 'show the TRC status for member X'. For documents use get_validation_evidence."""
        return await run_tool(tc, tool="get_member_trc_status", source="TRC Event Processor / GWDP", op=Op.GET_TRC_STATUS,
                              path={"memberId": member_id}, model=d.MemberTrcStatus, mapper=mappers.trc_status,
                              log_refs={"member": member_id})

    @mcp.tool(name="get_member_adt_timeline", annotations=READ, tags={"trc", "read", "member"})
    async def get_member_adt_timeline(
        member_id: MemberId,
        include_raw_hl7: Annotated[bool, Field(description="Include raw HL7 v2.5 segments (large). Default false.")] = False,
    ) -> Envelope[d.AdtTimeline]:
        """Ordered ADT event history (A01 admit, A02 transfer, A03 discharge) from ADT/HIE for ONE member."""
        return await run_tool(tc, tool="get_member_adt_timeline", source="ADT / HIE", op=Op.GET_ADT_EVENTS,
                              path={"memberId": member_id}, query={"includeRawHl7": True if include_raw_hl7 else None},
                              model=d.AdtTimeline, mapper=mappers.adt, log_refs={"member": member_id})

    @mcp.tool(name="get_risk_assessment", annotations=READ, tags={"trc", "read", "member"})
    async def get_risk_assessment(member_id: MemberId) -> Envelope[d.RiskAssessment]:
        """AI readmission-risk score, tier (HIGH >20%, MEDIUM 10-20%, LOW <10%) and contributing factors for ONE member.
        Score is for prioritization only."""
        return await run_tool(tc, tool="get_risk_assessment", source="EDS-EIS (Data Science risk model)", op=Op.GET_RISK,
                              path={"memberId": member_id}, model=d.RiskAssessment, mapper=mappers.risk, log_refs={"member": member_id})

    @mcp.tool(name="get_intervention_status", annotations=READ, tags={"trc", "read", "member"})
    async def get_intervention_status(member_id: MemberId) -> Envelope[d.InterventionStatus]:
        """Early-intervention status from Care Navi: state, coordinator, due date and activity log for ONE member."""
        return await run_tool(tc, tool="get_intervention_status", source="Care Navi", op=Op.GET_INTERVENTION,
                              path={"memberId": member_id}, model=d.InterventionStatus, mapper=mappers.intervention,
                              log_refs={"member": member_id})

    @mcp.tool(name="get_prior_admissions", annotations=READ, tags={"trc", "read", "member"})
    async def get_prior_admissions(member_id: MemberId) -> Envelope[d.PriorAdmissions]:
        """Prior admissions for the same member (facility, diagnosis, disposition, TRC outcome) for side-by-side comparison."""
        return await run_tool(tc, tool="get_prior_admissions", source="ADT / EDS-EIS", op=Op.GET_PRIOR_ADMISSIONS,
                              path={"memberId": member_id}, model=d.PriorAdmissions, mapper=mappers.prior, log_refs={"member": member_id})

    @mcp.tool(name="get_member_audit_trail", annotations=READ, tags={"trc", "read", "member", "audit"})
    async def get_member_audit_trail(member_id: MemberId) -> Envelope[d.AuditEvents]:
        """Full audit trail for ONE member's TRC task: notification events, record accesses, status transitions, escalations."""
        return await run_tool(tc, tool="get_member_audit_trail", source="TRC Event Processor / GWDP", op=Op.GET_AUDIT,
                              path={"memberId": member_id}, model=d.AuditEvents, mapper=mappers.audit, log_refs={"member": member_id})

    @mcp.tool(name="log_intervention_activity", annotations=WRITE, tags={"trc", "write", "member"})
    async def log_intervention_activity(
        member_id: MemberId,
        activity: Annotated[str, Field(min_length=3, max_length=500, description="Short activity note (e.g. 'Medication reconciliation call completed').")],
        idempotency_key: IdemKey = None,
    ) -> Envelope[d.InterventionLogResult]:
        """WRITE. Append one activity to a member's early-intervention log in Care Navi. Requires explicit user confirmation
        (enforced by the agent). Do not include PHI beyond what the user typed."""
        return await run_tool(tc, tool="log_intervention_activity", source="Care Navi", op=Op.LOG_INTERVENTION, scopes=(S_READ, S_WRITE),
                              path={"memberId": member_id}, body={"activity": activity}, write=True, idempotency_key=idempotency_key,
                              model=d.InterventionLogResult, mapper=mappers.intervention_log, log_refs={"member": member_id})
