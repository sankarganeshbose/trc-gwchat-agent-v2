"""Deterministic tool policy: the agent's allow-list and classification. LLM output never changes this."""
from __future__ import annotations

import re

GATEWAY_SEP = "___"  # AgentCore Gateway exposes tools as <targetName>___<toolName>

READ_TOOLS = frozenset({
    "get_trc_summary", "get_trc_metric_breakdown", "get_trc_worklist", "get_closure_board",
    "get_member_details", "get_member_trc_status", "get_member_adt_timeline", "get_risk_assessment",
    "get_intervention_status", "get_prior_admissions", "get_member_audit_trail",
    "get_discharge_summary", "get_discharge_medications", "get_followup_status",
    "get_provider_contacts", "get_provider_outreach", "list_provider_outreach",
    "get_validation_evidence", "get_validation_summary", "get_attachments", "get_mrat_review_status",
})
# Non-destructive, idempotent POSTs the user can trigger without a confirmation step
COMPUTE_TOOLS = frozenset({"validate_claims", "get_attachment_access_link"})
# State-changing: ALWAYS routed through the human-confirmation gate, never executed directly from an LLM tool call
WRITE_TOOLS = frozenset({
    "send_provider_notification", "resend_notifications_bulk", "escalate_to_provider_manager",
    "log_intervention_activity", "update_review_status", "request_worklist_export",
})
LOCAL_TOOLS = frozenset({"load_member_trc_record", "run_validation_and_load_closure_board"})
ALLOWED_MCP_TOOLS = READ_TOOLS | COMPUTE_TOOLS | WRITE_TOOLS

MEMBER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{4,24}$")

# tool -> business intent (used for response `intent` and metrics; deterministic, not LLM-classified)
INTENT_BY_TOOL = {
    "get_trc_summary": "TRC_DASHBOARD", "get_trc_metric_breakdown": "TRC_DASHBOARD",
    "get_trc_worklist": "TRC_WORKLIST", "get_closure_board": "TRC_CLOSURE_BOARD",
    "load_member_trc_record": "MEMBER_TRC_RECORD", "get_member_details": "MEMBER_TRC_RECORD",
    "get_member_trc_status": "MEMBER_TRC_STATUS", "get_member_adt_timeline": "MEMBER_ADT_TIMELINE",
    "get_risk_assessment": "MEMBER_RISK", "get_intervention_status": "MEMBER_INTERVENTION",
    "get_prior_admissions": "MEMBER_PRIOR_ADMISSIONS", "get_member_audit_trail": "MEMBER_AUDIT_TRAIL",
    "get_discharge_summary": "MEMBER_DISCHARGE", "get_discharge_medications": "MEMBER_DISCHARGE",
    "get_followup_status": "MEMBER_FOLLOWUP", "get_provider_contacts": "PROVIDER_CONTACT",
    "get_provider_outreach": "PROVIDER_NOTIFICATION_STATUS", "list_provider_outreach": "PROVIDER_NOTIFICATION_TRACKING",
    "get_validation_evidence": "VALIDATION_EVIDENCE", "get_validation_summary": "VALIDATION_RUN",
    "validate_claims": "VALIDATION_RUN", "run_validation_and_load_closure_board": "VALIDATION_RUN",
    "get_attachments": "MEDICAL_RECORDS", "get_attachment_access_link": "MEDICAL_RECORDS",
    "get_mrat_review_status": "MRAT_STATUS",
    "send_provider_notification": "ACTION_RESEND_NOTIFICATION", "resend_notifications_bulk": "ACTION_BULK_RESEND",
    "escalate_to_provider_manager": "ACTION_ESCALATE", "log_intervention_activity": "ACTION_LOG_INTERVENTION",
    "update_review_status": "ACTION_SOFT_CLOSE", "request_worklist_export": "ACTION_EXPORT",
}


def canonical(tool_name: str) -> str:
    """'trc-mcp___get_member_details' -> 'get_member_details'."""
    return tool_name.split(GATEWAY_SEP)[-1]
