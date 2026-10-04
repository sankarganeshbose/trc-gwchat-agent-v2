"""Payload models (the `data` of each Envelope). One section per MCP tool family."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from .common import (
    Channel, ClaimStatus, Contract, Disposition, Eligibility, ExportFormat, InterventionState,
    LineOfBusiness, MetricDimension, NotificationStatus, ProviderResponse, RecordSource, RecordType,
    ReviewStatusTarget, RiskTier, TrcStatus, UploadStatus,
)


# ═════════════════════════ cohort / dashboard ═════════════════════════
class FunnelStage(Contract):
    count: int
    rate: float | None = Field(None, description="Percent of discharges identified, 0-100.")


class RiskTierCount(Contract):
    tier: RiskTier
    count: int
    note: str | None = None


class TrcSummary(Contract):
    measurement_period: str
    discharges_identified: int
    provider_notified: FunnelStage
    validation_passed: FunnelStage
    soft_closed: FunnelStage
    mrat_final_closed: int
    no_upload_by_day3: int
    no_upload_by_day3_high_risk: int
    awaiting_mrat_closure: int
    closure_rate_pct: float
    prior_quarter_closure_rate_pct: float | None = None
    plan_target_pct: float | None = None
    active_window_members: int
    risk_tiers: list[RiskTierCount]


class MetricPoint(Contract):
    label: str
    numerator: float | None = None
    denominator: float | None = None
    value: float = Field(description="Rate (%) or count depending on dimension; see `unit`.")
    unit: str = "percent"


class MetricBreakdown(Contract):
    dimension: MetricDimension
    measurement_period: str
    points: list[MetricPoint]


class WorklistItem(Contract):
    member_id: str = Field(description="HCCID, e.g. HCC-4471829")
    member_name: str
    line_of_business: LineOfBusiness | None
    admit_date: date
    discharge_date: date
    facility: str
    diagnosis: str
    disposition: Disposition
    eligibility: Eligibility
    trc_status: TrcStatus
    risk_score: float | None
    risk_tier: RiskTier | None
    notification_status: NotificationStatus | None
    notification_channel: Channel | None
    provider_upload_status: UploadStatus
    followup_due: date | None
    days_since_discharge: int
    past_day3_no_upload: bool


class WorklistPage(Contract):
    items: list[WorklistItem]
    returned: int
    total_matching: int
    sort: str
    applied_filters: dict[str, str | int | bool]
    next_cursor: str | None = None


class ClosureCard(Contract):
    member_id: str
    member_name: str
    risk_tier: RiskTier | None
    trc_status: TrcStatus
    tag: str
    followup_due: date | None


class ClosureColumn(Contract):
    status: TrcStatus
    label: str
    count: int
    cards: list[ClosureCard]


class ClosureBoard(Contract):
    columns: list[ClosureColumn]


# ═════════════════════════ member / discharge ═════════════════════════
class MemberDetails(Contract):
    member_id: str
    name: str
    dob: date
    age: int
    gender: str
    mrn: str
    line_of_business: LineOfBusiness | None
    admit_at: datetime
    discharge_at: datetime
    facility: str
    facility_type: str
    admission_type: str
    diagnosis_code: str
    diagnosis_description: str
    disposition: Disposition
    eligibility: Eligibility
    ineligibility_reason: str | None = None
    trc_status: TrcStatus
    followup_due: date | None


class TrcStep(Contract):
    key: TrcStatus
    label: str
    state: str = Field(description="DONE | IN_PROGRESS | PENDING | FAILED")
    detail: str


class MemberTrcStatus(Contract):
    """The 'TRC Measure Status' tracker: Discharge Identified -> Provider Notified -> Validation Passed -> Soft Closed -> MRAT Final Closure."""

    member_id: str
    trc_status: TrcStatus
    eligibility: Eligibility
    ineligibility_reason: str | None = None
    steps: list[TrcStep]
    followup_due: date | None


class AdtEvent(Contract):
    event_type: str = Field(description="HL7 ADT trigger event, e.g. A01 / A02 / A03")
    label: str
    occurred_at: datetime
    location: str
    detail: str
    raw_hl7: str | None = Field(None, description="Only populated when include_raw_hl7=true.")


class AdtTimeline(Contract):
    member_id: str
    events: list[AdtEvent]
    source: str = "ADT/HIE (HL7 v2.5)"


class DischargeSummary(Contract):
    member_id: str
    diagnosis_code: str
    diagnosis_description: str
    disposition: Disposition
    facility: str
    source_documents: list[str]
    last_updated: datetime


class DischargeMedication(Contract):
    name: str
    dose: str
    frequency: str
    indication: str


class DischargeMedications(Contract):
    member_id: str
    medications: list[DischargeMedication]
    on_file: bool


class FollowupStatus(Contract):
    member_id: str
    followup_due: date | None
    days_until_due: int | None = Field(None, description="Negative => overdue.")
    overdue: bool
    recommendations: list[str]
    pcp_visit_confirmed: bool | None = None


class RiskAssessment(Contract):
    member_id: str
    score: float
    tier: RiskTier
    factors: list[str]
    model_note: str = "AI readmission-risk score used for prioritization only."


class InterventionActivity(Contract):
    description: str


class InterventionStatus(Contract):
    member_id: str
    status: InterventionState | None
    coordinator: str | None
    due_date: date | None
    activities: list[InterventionActivity]


class PriorAdmission(Contract):
    admit_date: date
    discharge_date: date
    facility: str
    diagnosis: str
    disposition: str
    trc_outcome: str


class PriorAdmissions(Contract):
    member_id: str
    admissions: list[PriorAdmission]


# ═════════════════════════ provider / notification ═════════════════════════
class ProviderContact(Contract):
    channel: Channel
    value: str | None = Field(None, description="Masked, e.g. 'fax ***-***-4410'.")
    verified: bool
    verified_on: date | None = None
    preferred: bool = False


class ProviderContacts(Contract):
    provider_id: str
    provider_name: str
    specialty: str | None
    contacts: list[ProviderContact]


class AuditEntry(Contract):
    at: datetime
    actor: str
    action: str
    detail: str | None = None


class ProviderOutreach(Contract):
    member_id: str
    notification_id: str | None
    provider_id: str | None
    provider_name: str | None
    event: str = "Discharge (A03)"
    status: NotificationStatus | None
    channel: Channel | None
    sent_at: datetime | None
    acknowledged_at: datetime | None
    provider_response: ProviderResponse | None
    vista_upload: UploadStatus
    vista_upload_date: date | None = None
    alert_fields: list[str] = Field(default_factory=list)
    proxy_task_updated: bool | None = None
    audit_trail: list[AuditEntry] = Field(default_factory=list)


class OutreachListItem(Contract):
    member_id: str
    member_name: str
    event: str
    provider_id: str | None
    provider_name: str | None
    facility: str
    channel: Channel | None
    sent_at: datetime | None
    status: NotificationStatus | None
    provider_response: ProviderResponse | None
    vista_upload: UploadStatus
    resend_allowed: bool = Field(description="True only for FAILED/PENDING (business rule from prototype).")


class OutreachPage(Contract):
    items: list[OutreachListItem]
    returned: int
    total_matching: int
    applied_filters: dict[str, str | int | bool]


class NotificationSendResult(Contract):
    notification_id: str
    member_id: str
    status: NotificationStatus
    channel: Channel
    proxy_task_updated: bool
    idempotent_replay: bool = False


class BulkSkip(Contract):
    member_id: str
    reason: str


class BulkResendResult(Contract):
    batch_id: str
    requested: int
    accepted: list[NotificationSendResult]
    skipped: list[BulkSkip]


class EscalationResult(Contract):
    escalation_id: str
    member_id: str
    notification_id: str | None
    escalated_to: str | None
    idempotent_replay: bool = False


# ═════════════════════════ validation / closure / records ═════════════════════════
class EvidenceItem(Contract):
    name: str
    source_system: str
    available: bool
    detail: str | None = None


class ValidationEvidence(Contract):
    member_id: str
    window_days: int = 3
    upload_status: UploadStatus
    upload_date: date | None
    claim_status: ClaimStatus
    claim_date: date | None
    care_navi_task_status: str | None
    items: list[EvidenceItem]
    rule_outcome: str = Field(description="PASSED | FAILED | PENDING as reported by the rules engine.")


class ValidationResult(Contract):
    member_id: str
    outcome: str = Field(description="PASSED | FAILED | PENDING")
    reasons: list[str]
    checked_at: datetime
    eligible_for_soft_closure: bool


class ValidationRun(Contract):
    run_id: str
    results: list[ValidationResult]
    evaluated: int
    passed: int
    failed: int
    persisted: bool = Field(description="Whether the on-prem rules engine recorded this run.")


class ValidationSummary(Contract):
    window_days: int
    evaluated_last_90_days: int
    notified_within_1_day_pct: float
    records_uploaded_by_day3_pct: float
    claims_validated_pct: float
    passed_soft_closed_pct: float
    failed_pct: float
    avg_days_discharge_to_soft_close: float
    awaiting_mrat_final_closure: int


class Attachment(Contract):
    attachment_id: str
    member_id: str
    member_name: str | None = None
    name: str
    record_type: RecordType
    source: RecordSource
    date: date
    status: str = Field(description="COMPLETE | PARTIAL")
    read_only: bool = True


class AttachmentList(Contract):
    items: list[Attachment]
    returned: int
    applied_filters: dict[str, str | int | bool]
    note: str = "Read-only. System of record remains EIP / Content Central / Provider Vista."


class AttachmentAccessLink(Contract):
    attachment_id: str
    url: str = Field(description="Short-lived on-prem viewer URL. Document bytes never transit AWS.")
    expires_at: datetime
    read_only: bool = True
    audit_logged: bool = True


class MratReviewStatus(Contract):
    member_id: str
    trc_status: TrcStatus
    awaiting_final_closure: bool
    assigned_nurse: str | None
    mrat_deeplink: str | None
    closed_at: datetime | None


class AuditEvents(Contract):
    member_id: str
    events: list[AuditEntry]


class InterventionLogResult(Contract):
    activity_id: str
    member_id: str
    idempotent_replay: bool = False


class ReviewStatusResult(Contract):
    member_id: str
    previous_status: TrcStatus
    new_status: TrcStatus
    transition_id: str
    requested_target: ReviewStatusTarget
    idempotent_replay: bool = False


class ExportJob(Contract):
    job_id: str
    format: ExportFormat
    status: str = Field(description="QUEUED | READY | FAILED")
    row_count: int | None = None
    download_url: str | None = Field(None, description="Short-lived on-prem URL; file is generated on-prem.")
    expires_at: datetime | None = None
