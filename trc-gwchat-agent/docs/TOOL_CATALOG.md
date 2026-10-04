# MCP tool catalog (generated)

29 tools · Envelope `{ok, data, error, meta}` on every response · routes are PLACEHOLDERS (override via `TRC_MCP_ENDPOINT_OVERRIDES_JSON`).

| Tool | Class | Required inputs | Optional inputs | On-prem route (placeholder) | Source system | Idempotency |
|---|---|---|---|---|---|---|
| `get_attachments` | READ | — | `member_id`, `record_type`, `source`, `limit` | `GET /api/trc/attachments` | Provider Vista / EIP / Content Central | n/a (GET) |
| `get_closure_board` | READ | — | — | `GET /api/trc/closure-board` | TRC Event Processor / GWDP | n/a (GET) |
| `get_discharge_medications` | READ | `member_id` | — | `GET /api/trc/discharges/{memberId}/medications` | EIP / CCDA | n/a (GET) |
| `get_discharge_summary` | READ | `member_id` | — | `GET /api/trc/discharges/{memberId}` | ADT / HIE + EIP | n/a (GET) |
| `get_followup_status` | READ | `member_id` | — | `GET /api/trc/members/{memberId}/followup` | Care Navi / ADT | n/a (GET) |
| `get_intervention_status` | READ | `member_id` | — | `GET /api/trc/members/{memberId}/intervention` | Care Navi | n/a (GET) |
| `get_member_adt_timeline` | READ | `member_id` | `include_raw_hl7` | `GET /api/trc/members/{memberId}/adt-events` | ADT / HIE | n/a (GET) |
| `get_member_audit_trail` | READ | `member_id` | — | `GET /api/trc/audit/{memberId}` | TRC Event Processor / GWDP | n/a (GET) |
| `get_member_details` | READ | `member_id` | — | `GET /api/trc/members/{memberId}` | EDS-EIS / ADT | n/a (GET) |
| `get_member_trc_status` | READ | `member_id` | — | `GET /api/trc/members/{memberId}/status` | TRC Event Processor / GWDP | n/a (GET) |
| `get_mrat_review_status` | READ | `member_id` | — | `GET /api/trc/closure/{memberId}` | MRAT | n/a (GET) |
| `get_prior_admissions` | READ | `member_id` | — | `GET /api/trc/members/{memberId}/prior-admissions` | ADT / EDS-EIS | n/a (GET) |
| `get_provider_contacts` | READ | `provider_id` | — | `GET /api/trc/provider/{providerId}` | Provider Directory | n/a (GET) |
| `get_provider_outreach` | READ | `member_id` | — | `GET /api/trc/notifications/{memberId}` | Notification Processor / Provider Vista | n/a (GET) |
| `get_risk_assessment` | READ | `member_id` | — | `GET /api/trc/members/{memberId}/risk` | EDS-EIS (Data Science risk model) | n/a (GET) |
| `get_trc_metric_breakdown` | READ | `dimension` | — | `GET /api/trc/metrics/{dimension}` | TRC Event Processor / GWDP | n/a (GET) |
| `get_trc_summary` | READ | — | — | `GET /api/trc/summary` | TRC Event Processor / GWDP | n/a (GET) |
| `get_trc_worklist` | READ | — | `query`, `eligibility`, `disposition`, `trc_status`, `provider_upload_status`, `risk_tier`, `facility`, `line_of_business`, `discharge_from`, `discharge_to`, `lookback_days`, `past_day3_no_upload_only`, `sort_by`, `limit`, `cursor` | `GET /api/trc/worklist` | TRC Event Processor / GWDP | n/a (GET) |
| `get_validation_evidence` | READ | `member_id` | — | `GET /api/trc/validation/{memberId}` | Provider Vista + Claims + Care Navi | n/a (GET) |
| `get_validation_summary` | READ | — | — | `GET /api/trc/validation-summary` | Validation Agent / GWDP | n/a (GET) |
| `list_provider_outreach` | READ | — | `status`, `channel`, `facility`, `provider_response`, `unacknowledged_only`, `limit` | `GET /api/trc/notifications` | Notification Processor | n/a (GET) |
| `escalate_to_provider_manager` | WRITE | `member_id`, `reason` | `idempotency_key` | `POST /api/trc/escalations` | Notification Processor | ticket-derived key (agent) / auto key (server) |
| `get_attachment_access_link` | COMPUTE | `attachment_id` | — | `POST /api/trc/attachments/{attachmentId}/access-link` | EIP / Content Central | idempotent run record |
| `log_intervention_activity` | WRITE | `member_id`, `activity` | `idempotency_key` | `POST /api/trc/interventions/{memberId}/activities` | Care Navi | ticket-derived key (agent) / auto key (server) |
| `request_worklist_export` | WRITE | `format` | `trc_status`, `risk_tier`, `provider_upload_status`, `disposition`, `eligibility`, `idempotency_key` | `POST /api/trc/exports` | TRC Event Processor / GWDP | ticket-derived key (agent) / auto key (server) |
| `resend_notifications_bulk` | WRITE | `member_ids`, `reason` | `idempotency_key` | `POST /api/trc/notifications/bulk-resend` | Notification Processor | ticket-derived key (agent) / auto key (server) |
| `send_provider_notification` | WRITE | `member_id`, `reason` | `channel`, `idempotency_key` | `POST /api/trc/notifications` | Notification Processor | ticket-derived key (agent) / auto key (server) |
| `update_review_status` | WRITE | `member_id`, `target_status`, `reason` | `idempotency_key` | `POST /api/trc/closure` | TRC Event Processor / MRAT | ticket-derived key (agent) / auto key (server) |
| `validate_claims` | COMPUTE | — | `member_ids` | `POST /api/trc/validation/claims` | Validation Agent / Claims | idempotent run record |

## Per-tool descriptions (what the LLM sees)

### `get_attachments`

List TRC medical records/attachments (discharge summaries, CCDAs, progress notes, labs, imaging, provider notifications, claim matches)
from Provider Vista / Link, EIP, Content Central and Claims. READ-ONLY metadata; every access is audit-logged on-prem
(requires scope trc.records.read). Omit member_id to list across the worklist.

### `get_closure_board`

Kanban view of measure status: Discharge Identified -> Provider Notified -> Validation Passed -> Soft Closed/MRAT,
with member cards per column. Read-only; does not run validation (use validate_claims for that).

### `get_discharge_medications`

Discharge medication list (name, dose, frequency, indication) for ONE member. `on_file=false` means none on file
— it does NOT mean the member has no medications. Supports medication-reconciliation review.

### `get_discharge_summary`

Discharge diagnosis, disposition, discharging facility, source documents (ADT A03 + CCDA) and last-updated time for ONE member.

### `get_followup_status`

PCP follow-up timeframe for ONE member: due date, days until due (negative = overdue), overdue flag,
discharge follow-up recommendations and whether a PCP visit is confirmed.

### `get_intervention_status`

Early-intervention status from Care Navi: state, coordinator, due date and activity log for ONE member.

### `get_member_adt_timeline`

Ordered ADT event history (A01 admit, A02 transfer, A03 discharge) from ADT/HIE for ONE member.

### `get_member_audit_trail`

Full audit trail for ONE member's TRC task: notification events, record accesses, status transitions, escalations.

### `get_member_details`

Demographics, admission (facility, type, dates), principal diagnosis, disposition, TRC eligibility (with exclusion reason,
e.g. EXPIRED), current TRC status and PCP follow-up due date for ONE member.

### `get_member_trc_status`

Current TRC measure status for ONE member as the 5-step tracker (Discharge Identified, Provider Notified, Validation Passed,
Soft Closed, MRAT Final Closure) with each step's state (DONE / IN_PROGRESS / PENDING / FAILED) and evidence detail, plus
eligibility (and exclusion reason). Use for 'show the TRC status for member X'. For documents use get_validation_evidence.

### `get_mrat_review_status`

MRAT review state for ONE member: awaiting HEDIS-nurse final closure?, assigned nurse pool, MRAT deep link ('View Details / MRAT
Closure'), closed-at. Read-only.

### `get_prior_admissions`

Prior admissions for the same member (facility, diagnosis, disposition, TRC outcome) for side-by-side comparison.

### `get_provider_contacts`

Verified provider contact channels (fax / email / provider proxy task) from Provider Directory, with verification date and
preferred channel. Values are masked. Use before resending an alert or to answer 'how will we reach Dr. X'.

### `get_provider_outreach`

Provider notification status for ONE member: provider, channel, sent/ack times, provider response, Provider Vista
upload status, alert content fields, whether the Proxy Task was updated, and the audit trail.

### `get_risk_assessment`

AI readmission-risk score, tier (HIGH >20%, MEDIUM 10-20%, LOW <10%) and contributing factors for ONE member.
Score is for prioritization only.

### `get_trc_metric_breakdown`

One dashboard breakdown (chart/table data) for the TRC measure. Choose exactly one dimension per call.

### `get_trc_summary`

TRC dashboard snapshot for the measurement period: discharges identified, provider-notified / validation-passed /
soft-closed counts and rates, members with no Provider Vista upload by day 3 (and how many are HIGH risk),
awaiting-MRAT count, closure rate vs prior quarter and plan target, and risk-tier distribution.
Use for 'how are we doing on TRC' / KPI questions. Not for member-level detail (use get_trc_worklist).

### `get_trc_worklist`

TRC worklist: one row per TRC discharge with measure status, risk, provider-notification status and Provider Vista
upload status. Supports every filter in the GWChat worklist UI. Use for 'show members discharged in the last N days where the provider has not
uploaded documents by day 3 ranked by risk' (lookback_days=N, past_day3_no_upload_only=true, sort_by=risk_score_desc),
and for 'list all members on the TRC worklist'. Returns a page; use `total_matching` vs `returned` to report truncation.

### `get_validation_evidence`

Validation evidence for ONE member: Provider Vista upload, claim match in the 3-day window, Care Navi task status and
the evidence checklist (discharge summary, provider notification, provider records, claim match) with the rules-engine outcome.
Does NOT re-run validation (use validate_claims).

### `get_validation_summary`

Aggregate Deterministic Validation Agent metrics (tasks evaluated, % notified <=1 day, % records uploaded by day 3,
% claims validated, % passed->soft closed, % failed, avg days to soft closure, awaiting MRAT).

### `list_provider_outreach`

Cohort view of TRC provider notifications (admission A01 / discharge A03 alerts) with filters. Use for 'which providers have not
acknowledged their TRC discharge notifications?' (unacknowledged_only=true). Each row has `resend_allowed`.

### `escalate_to_provider_manager`

WRITE. Escalate a member's non-responsive/failed provider notification to the facility's Provider Manager.
Requires explicit user confirmation (enforced by the agent).

### `get_attachment_access_link`

Get a short-lived, read-only, audit-logged on-prem viewer URL for ONE attachment (UI 'View'). Document content is never returned by MCP.

### `log_intervention_activity`

WRITE. Append one activity to a member's early-intervention log in Care Navi. Requires explicit user confirmation
(enforced by the agent). Do not include PHI beyond what the user typed.

### `request_worklist_export`

Create an on-prem export job for the filtered worklist (UI 'Export CSV/PDF'). The file is generated and hosted ON-PREM; the
result is a short-lived download URL, never file bytes. Audit-logged on-prem.

### `resend_notifications_bulk`

WRITE. Resend alerts for an EXPLICIT list of members (UI: 'Bulk Resend to Non-Responsive'). Compose the list from
list_provider_outreach first and show it to the user. Per-member rule failures are returned in `skipped`, not raised.
Requires explicit user confirmation (enforced by the agent).

### `send_provider_notification`

WRITE. Resend ONE standardized TRC provider alert for a member whose alert is FAILED or PENDING. On-prem enforces that
other statuses are rejected (PRECONDITION_FAILED) and updates the Proxy Task after sending. Requires explicit user
confirmation (enforced by the agent).

### `update_review_status`

WRITE. Soft-close ONE member's TRC task (VALIDATION_PASSED -> SOFT_CLOSED), which routes it to the MRAT queue for HEDIS-nurse
final validation. On-prem rejects any other transition (PRECONDITION_FAILED). Cannot set MRAT_CLOSED. Requires explicit
user confirmation (enforced by the agent).

### `validate_claims`

Run the deterministic, rule-based validation (Provider Vista upload present + claim matched within the 3-day window + Care
Navi task) and return a per-member outcome. Rules live on-prem; this tool never decides outcomes itself. It does NOT soft-close
anything (see update_review_status). Idempotent. Used for 'run the validation agent' and 'Re-run validate_claims()'.

