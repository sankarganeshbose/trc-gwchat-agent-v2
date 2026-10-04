"""Deterministic GWChat response assembly from the ledger. No LLM involved."""
from __future__ import annotations

import json

from ..models.schemas import Block, BlockType, DataGap, ResponseStatus, ToolTrace
from ..policy import INTENT_BY_TOOL, WRITE_TOOLS
from .ledger import ToolLedger, ToolRecord

SINGLE: dict[str, tuple[BlockType, str]] = {
    "get_trc_summary": (BlockType.KPI_SUMMARY, "TRC snapshot"),
    "get_trc_metric_breakdown": (BlockType.METRIC_BREAKDOWN, "TRC metric breakdown"),
    "get_trc_worklist": (BlockType.WORKLIST, "TRC worklist"),
    "get_closure_board": (BlockType.CLOSURE_BOARD, "TRC closure board"),
    "list_provider_outreach": (BlockType.NOTIFICATIONS, "Provider notification tracking"),
    "validate_claims": (BlockType.VALIDATION_RUN, "Validation run"),
    "get_validation_summary": (BlockType.VALIDATION_SUMMARY, "Validation summary"),
    "get_attachments": (BlockType.RECORDS, "Medical records & attachments"),
    "get_attachment_access_link": (BlockType.RECORD_LINK, "Record viewer link"),
    "get_provider_contacts": (BlockType.PROVIDER_CONTACTS, "Provider contacts"),
    "get_mrat_review_status": (BlockType.MRAT_STATUS, "MRAT review status"),
}
MEMBER_SCOPED = {"get_member_details", "get_member_trc_status", "get_member_adt_timeline", "get_risk_assessment", "get_intervention_status",
                 "get_prior_admissions", "get_member_audit_trail", "get_discharge_summary", "get_discharge_medications",
                 "get_followup_status", "get_provider_outreach", "get_validation_evidence"}


def _block(rec: ToolRecord, btype: BlockType, title: str, section: str | None = None) -> Block:
    return Block(type=btype, title=title, section=section, source_tools=[rec.tool],
                 source_systems=[rec.meta.get("source_system")] if rec.meta.get("source_system") else [],
                 as_of=rec.meta.get("as_of"), data=rec.data or {})


def build_blocks(ledger: ToolLedger) -> list[Block]:
    blocks: list[Block] = []
    plan_member_sections: dict[str, ToolRecord] = {}
    seen: set[str] = set()
    for rec in ledger.records:
        if not rec.ok:
            continue
        key = rec.tool + json.dumps(rec.args, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        if rec.origin == "executor" or rec.tool in WRITE_TOOLS:
            blocks.append(_block(rec, BlockType.ACTION_RESULT, f"Action result — {rec.tool}"))
        elif rec.origin == "plan" and rec.section and rec.tool in MEMBER_SCOPED | {"get_attachments", "get_provider_contacts"} and rec.args.get("member_id", rec.args.get("provider_id")):
            plan_member_sections[rec.section] = rec
        elif rec.tool in MEMBER_SCOPED:
            blocks.append(_block(rec, BlockType.MEMBER_SECTION, rec.tool.replace("get_", "").replace("_", " ").title(), rec.tool))
        elif rec.tool in SINGLE:
            btype, title = SINGLE[rec.tool]
            blocks.append(_block(rec, btype, title))
    if plan_member_sections:
        any_rec = next(iter(plan_member_sections.values()))
        det = plan_member_sections.get("details")
        title = f"TRC record — {det.data['member_id']}" if det and det.data else "TRC record"
        blocks.insert(0, Block(
            type=BlockType.MEMBER_RECORD, title=title, source_tools=[r.tool for r in plan_member_sections.values()],
            source_systems=sorted({r.meta.get("source_system") for r in plan_member_sections.values() if r.meta.get("source_system")}),
            as_of=any_rec.meta.get("as_of"), data={sec: r.data for sec, r in plan_member_sections.items()}))
    return blocks


def build_gaps(ledger: ToolLedger) -> list[DataGap]:
    gaps = []
    for r in ledger.failures():
        e = r.error or {}
        gaps.append(DataGap(tool=r.tool, section=r.section, code=e.get("code", "UNKNOWN"),
                            message=e.get("message", "Data unavailable."), retryable=bool(e.get("retryable"))))
    return gaps


def build_trace(ledger: ToolLedger) -> list[ToolTrace]:
    out = [ToolTrace(tool=r.tool, ok=r.ok, outcome="ok" if r.ok else "failed", latency_ms=r.duration_ms,
                     error_code=(r.error or {}).get("code"), request_id=r.meta.get("request_id")) for r in ledger.records]
    out += [ToolTrace(tool=t, ok=False, outcome="blocked", error_code=c) for t, c in ledger.blocked]
    out += [ToolTrace(tool=p.tool, ok=True, outcome="queued_for_confirmation") for p in ledger.pending]
    return out


def derive_intent(ledger: ToolLedger) -> str:
    labelled = [r.intent or INTENT_BY_TOOL.get(r.tool, "UNKNOWN") for r in ledger.records] + [INTENT_BY_TOOL.get(p.tool, "UNKNOWN") for p in ledger.pending]
    intents = list(dict.fromkeys(labelled))
    if not intents:
        return "NO_TOOL_INTENT"
    return intents[0] if len(intents) == 1 else "+".join(intents[:3])


def derive_status(ledger: ToolLedger, blocks: list[Block], gaps: list[DataGap]) -> ResponseStatus:
    if ledger.pending:
        return ResponseStatus.NEEDS_CONFIRMATION
    if not ledger.records:
        return ResponseStatus.NARRATIVE_ONLY
    if blocks and not gaps:
        return ResponseStatus.OK
    return ResponseStatus.PARTIAL if blocks else ResponseStatus.UNAVAILABLE


def fallback_summary(blocks: list[Block], gaps: list[DataGap]) -> str:
    """Deterministic message used when the LLM narrative fails the grounding check."""
    parts = [f"Retrieved: {', '.join(b.title for b in blocks)}." if blocks else "No data could be retrieved."]
    if gaps:
        parts.append("Unavailable: " + "; ".join(f"{g.section or g.tool} ({g.code})" for g in gaps) + ".")
    return " ".join(parts)
