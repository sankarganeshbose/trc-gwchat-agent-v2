# 1 · Architecture interpretation, prototype inventory and mappings

Inputs analysed: `HEDIS Measure Gap – TRC (Transition of Care)_Draft.pptx` (authoritative architecture), `GuideWellChat_TRC_HEDIS_Prototype_Draft.html` (user-facing behaviour), and `HEDIS_TRC_GWChat_Integration_Agent_Technical_Design.docx` (engineering baseline, reconciled in §1.4).

## 1.1 What the GWChat Integration Agent is — and is not

The deck shows one box labelled **GWChat Integration Agent (Status & Display)** on **AgentCore Runtime**, connected through **MCP → AgentCore Gateway** to on-prem processors and databases ("Connects MCP tools to GuideWell On-Prem APIs"). Its named tool surface is `validate_claims()`, `get_trc_worklist()`, `get_member_details()`, `get_provider_outreach()`, `get_validation_evidence()`, `get_attachments()`, `update_review_status()`. The prototype shows the same seven names in its tool-call traces.

**Responsible for**

| Area | What it does |
|---|---|
| Intent | Understand a TRC question or action from GWChat (6 scripted prompts + ~16 UI actions, §1.2). |
| Tool selection | Choose the minimum set of MCP tools; issue independent reads together (parallel); sequence dependent ones. |
| Orchestration | Deterministic playbooks for the two heavy flows (full member record, validate→board). |
| Grounding | Everything shown as data comes verbatim from tool results; missing data is reported as a *data gap*, never inferred. |
| Write safety | Propose state-changing actions; execute only after a signed, user-bound human confirmation. |
| Response | One structured `GWChatResponse` (blocks + short narrative + gaps + pending actions + trace). |

**Not responsible for** (deliberately out of scope): the ADT Event Processor, TRC Event Processor / Proxy Task creation, Notification Processor delivery (email/fax), the Deterministic Validation Agent's rules, MRAT and the HEDIS nurse's final closure, the risk model, the GWChat UI, any AWS data store. It never calls on-prem APIs, never holds member data beyond one request, and cannot final-close a measure.

## 1.2 Integration boundaries and data ownership

```
GWChat ─▶ AgentCore Runtime: GWChat Integration Agent (Strands) ─▶ AgentCore Gateway ─▶ FastMCP tools ─▶ on-prem REST ─▶ ADT/HIE · Care Navi · EDS-EIS · Provider Directory/Vista/Link · Claims · MRAT · Notification/TRC processors
   UI/UX        intent · tool choice · orchestration · guardrails      MCP boundary    typed deterministic contracts      source systems (system of record)
```

| Boundary | Rule |
|---|---|
| Data at rest | **Nothing is persisted in AWS.** No S3/RDS/OpenSearch/vector DB/AgentCore Memory for clinical facts. State is request-scoped; confirmation tickets are stateless (HMAC-signed). |
| Records | Document bytes never cross to AWS: `get_attachments` returns metadata, `get_attachment_access_link` returns a short-lived on-prem viewer URL. Exports are generated on-prem (`request_worklist_export` returns a link). |
| Identity | End-user (Entra ID, OAuth/JWT per deck) identity is propagated Agent → Gateway → MCP → on-prem (`X-On-Behalf-Of`) so on-prem audit logging ("All views are audit-logged") attributes the real user. |
| Business rules | Eligibility, validation (3-day window), resend allowed-states, valid status transitions live **on-prem**; MCP re-checks only cheap invariants (caps, enums) as defence in depth. |
| Closure | Soft closure may be requested by the agent; **final MRAT closure is human-only** — `MRAT_CLOSED` is not a legal tool argument. |

## 1.3 Prototype prompt & action inventory

### Scripted conversational prompts (the `TURNS` array)

| # | Prompt (verbatim intent) | Data the UI renders | Source systems | Read/Write | Deterministic? | Multi-call? |
|---|---|---|---|---|---|---|
| P1 | "Show me members admitted or discharged in the last 14 days where the provider has not uploaded any documents in Provider Vista by the third day, ranked by highest risk." | TRC KPI snapshot (1,284 / 96.0% / 37 / 58.0%) + highest-risk member cards | ADT/HIE, Provider Vista/Link, Claims, Care Navi, risk model | Read | Yes (filters + sort on-prem) | Yes (2, parallel) |
| P2 | "List all members on the TRC worklist with their measure status, sorted by risk score." | Worklist cards/table; filters: search, eligibility, disposition, TRC status, upload, risk tier | TRC Event Processor/GWDP | Read | Yes | No |
| P3 | "Open the TRC record for Dorothy Simmons (HCC-4471829) — show the measure status, validation evidence and ADT timeline." | 7 tabs: TRC Measure Status (+ evidence), ADT Timeline, Discharge Summary (+ meds, follow-ups), Risk & Follow-up (+ intervention), Provider Notification (+ audit trail), Prior Admissions, Medical Records | EDS-EIS, ADT, Care Navi, Notification Processor, Provider Vista, Claims, EIP/Content Central | Read | Yes | Yes (13, 12 parallel + 1 dependent) |
| P4 | "Which providers have not acknowledged their TRC discharge notifications?" | Notification tracking table (member, event, provider, channel, sent, status, response, Vista upload, Resend) | Notification Processor, Provider Vista | Read | Yes | No |
| P5 | "Run the validation agent and show me the TRC closure board." | Validation outcomes, summary KPIs (460 evaluated … 61 awaiting MRAT), 4-column Kanban | Deterministic Validation Agent, Claims, Provider Vista, Care Navi | Compute + Read | **Yes — rule-based** | Yes (sequential then parallel) |
| P6 | "Pull the uploaded medical records and attachments for MRAT review." | Read-only records list; member/type/source filters; audit-logged | Provider Vista/Link, EIP, Content Central, Claims | Read (audit-logged) | Yes | No |

> **Source discrepancy to resolve:** the deck says "last **3** days", the prototype prompt says "last **14** days", and its narration says "last **10** days". The design therefore makes the window a parameter (`lookback_days`) rather than a constant.

### UI actions that are not typed prompts (each can arrive via GWChat as an intent)

| # | Action (where) | Intent | Class |
|---|---|---|---|
| A1 | Open Full Dashboard → charts/tables (trend, disposition mix, component compliance, facility gaps) | dashboard breakdowns | Read |
| A2 | Apply Filters (date range, facility, LOB) | worklist filters | Read |
| A3 | Click a risk-tier KPI (HIGH/MEDIUM/LOW) | worklist by tier | Read |
| A4 | Click a member card / Kanban card | open member record (= P3) | Read |
| A5 | Search box (name / HCCID / MRN) | worklist `query` | Read |
| A6 | Export CSV / Export PDF | worklist export job | **Write** (on-prem file generation, audit) |
| A7 | Re-run `validate_claims()` (member detail) | per-member validation | Compute |
| A8 | View Details / MRAT Closure | MRAT status + deep link | Read |
| A9 | Resend Notification (member detail / table row) | resend one alert (FAILED/PENDING only) | **Write** |
| A10 | Escalate to Provider Manager | escalation | **Write** |
| A11 | View Full Audit Trail | member audit events | Read |
| A12 | + Log Intervention Activity | Care Navi activity | **Write** |
| A13 | Bulk Resend to Non-Responsive | list non-responsive → resend N | **Write** |
| A14 | Medical records "View 🔒" | short-lived on-prem viewer link | Compute (audit-logged) |
| A15 | Records member selector / type / source filters | attachments filter | Read |
| A16 | Soft closure ("Task update & soft closure"; `update_review_status()` syncs status) | soft-close a validated task | **Write** |
| — | Model selector, reasoning effort, sidebar (calendar/Teams/ARB search), "Link to Chat", "Back to Members", Cards/Table toggle | GWChat shell/UI only | not an agent concern |
| — | "Connecting to GuideWell data sources" trace: ADT Event Processor, TRC Event Processor (Proxy Tasks) | platform processors; run independently of chat | not agent tools |

### Gaps found between the prototype/baseline and what the data supports
* **Medication reconciliation status** — the prototype shows the discharge medication *list* and a cohort-level "Medication Reconciliation Post-Discharge" rate, **not** a per-member reconciliation-completed flag. No tool invents one; `get_discharge_medications` + the cohort metric are provided and a per-member API is an open item (§13 of doc 3).
* **TCM eligibility** — the prototype has *TRC* eligibility (ELIGIBLE/INELIGIBLE with exclusion reason, e.g. EXPIRED), exposed inside `get_member_details` / `get_member_trc_status`. No separate TCM tool is warranted by the prototype.
* **Per-discharge ids** — the prototype keys everything by member (HCCID); the baseline's `discharge_id`/`event_id` are not visible. If on-prem exposes them, add an optional `discharge_id` parameter (backwards compatible).
* **Data-shape quirks** in the mock data (an em-dash `—` for "no date"/"no coordinator", `N/A` upload/claim for excluded members) are normalised in `adapters/mappers.py`, which is exactly the kind of drift the adapter layer exists to absorb.

## 1.4 Reconciliation with the Technical Design docx

| Technical Design baseline | Outcome here |
|---|---|
| Principles: separation of reasoning/execution, grounded, fail-closed, narrow tools, replaceable adapters | Adopted unchanged (enforced in code: §5/§6 of doc 2). |
| Request-scoped agent state, no persisted clinical memory (§8.3) | Adopted: a **new Agent per request**; GWChat passes explicit `context`; confirmations use **stateless signed tickets**. |
| System-prompt rules 1-10 (§8.2) | Adopted verbatim in spirit as rules 1-10; rules 11-16 added from prototype findings (scope, MRAT, prompt-injection, output brevity). |
| Baseline tool names (`get_member_trc_status`, `get_discharge_details`, `get_follow_up_status`, `get_tcm_eligibility`, `get_provider_information`, `get_provider_contact_information`, `get_medication_reconciliation_status`, `get_notification_status`, `send_provider_notification`, `get_trc_closure_evidence`, `get_trc_worklist`) | The doc itself says to reconcile against the prototype. Mapping: `get_member_trc_status` ✔ (same name); `get_discharge_details` → `get_discharge_summary` (+ `get_member_adt_timeline`); `get_follow_up_status` → `get_followup_status`; `get_tcm_eligibility` → folded into member status/details (no TCM concept in prototype); `get_provider_information` + `get_provider_contact_information` → `get_provider_outreach` + `get_provider_contacts`; `get_medication_reconciliation_status` → **not supported by prototype** (`get_discharge_medications` instead); `get_notification_status` → `get_provider_outreach` / `list_provider_outreach`; `send_provider_notification` ✔ (same name, confirmation-gated); `get_trc_closure_evidence` → `get_validation_evidence` + `get_mrat_review_status` + `get_attachments`; `get_trc_worklist` ✔. The remaining tools come from the deck's seven named functions and the prototype's actions (summary, metric breakdowns, closure board, risk, intervention, prior admissions, audit trail, `validate_claims`, escalate, bulk resend, export, soft close, record links, …) — 29 in total. |
| Project layout `agent/`, `mcp/` | Renamed `trc_agent`, `trc_mcp`, `trc_contracts`: a top-level package called **`mcp`** would shadow the `mcp` PyPI package that FastMCP and Strands import. Added `orchestration/`, `services/`, `adapters/`, Dockerfiles, `tests/integration/`. |
| FastMCP location (§24: on-prem or another approved runtime?) | Kept as an explicit open decision with two supported deployments (doc 3 §9.4). Code is identical either way. |
| "Agent determines tools … composite review: 5 calls" | Generalised: 13-call member record with an explicit DAG (12 parallel + 1 dependent). |
| Error table (§11), idempotency for writes, PHI-safe logs, correlation id | Implemented and tested (see test evidence in doc 3). |

## 1.5 Prompt → Agent intent → MCP tool(s) → on-prem API → response

(`*` = business dependency → sequential; everything else in a row runs in parallel. Routes are **placeholders**; overrides via `TRC_MCP_ENDPOINT_OVERRIDES_JSON`.)

| Prompt / action | Agent intent | MCP tool(s) | On-prem API (placeholder) | Response block |
|---|---|---|---|---|
| P1 | `TRC_DASHBOARD+TRC_WORKLIST` | `get_trc_summary` ‖ `get_trc_worklist(lookback_days, past_day3_no_upload_only, sort_by=risk_score_desc)` | `GET /api/trc/summary` ‖ `GET /api/trc/worklist?lookbackDays=&pastDay3Only=true&sort=riskScore:desc` | `KPI_SUMMARY` + `WORKLIST` |
| P2, A2, A3, A5 | `TRC_WORKLIST` | `get_trc_worklist(filters…)` | `GET /api/trc/worklist?…` | `WORKLIST` |
| P3, A4 | `MEMBER_TRC_RECORD` | local composite `load_member_trc_record` → `get_member_details` ‖ `get_member_trc_status` ‖ `get_validation_evidence` ‖ `get_member_adt_timeline` ‖ `get_discharge_summary` ‖ `get_discharge_medications` ‖ `get_followup_status` ‖ `get_risk_assessment` ‖ `get_intervention_status` ‖ `get_prior_admissions` ‖ `get_provider_outreach` ‖ `get_attachments(member)` → `get_provider_contacts`* | `GET /api/trc/members/{id}` · `/status` · `/adt-events` · `/followup` · `/risk` · `/intervention` · `/prior-admissions`; `GET /api/trc/validation/{id}`; `GET /api/trc/discharges/{id}` (+ `/medications`); `GET /api/trc/notifications/{id}`; `GET /api/trc/attachments?memberId=`; `GET /api/trc/provider/{providerId}` | `MEMBER_RECORD` (13 sections) |
| "Show TRC status for member X" | `MEMBER_TRC_STATUS` | `get_member_trc_status` | `GET /api/trc/members/{id}/status` | `MEMBER_SECTION` |
| P4 | `PROVIDER_NOTIFICATION_TRACKING` | `list_provider_outreach(unacknowledged_only=true)` | `GET /api/trc/notifications?unacknowledged=true` | `NOTIFICATIONS` |
| P5 | `VALIDATION_RUN` | composite `run_validation_and_load_closure_board` → `validate_claims`* → `get_closure_board` ‖ `get_validation_summary` | `POST /api/trc/validation/claims` → `GET /api/trc/closure-board` ‖ `GET /api/trc/validation-summary` | `VALIDATION_RUN` + `CLOSURE_BOARD` + `VALIDATION_SUMMARY` |
| P6, A15 | `MEDICAL_RECORDS` | `get_attachments(member_id?, record_type?, source?)` | `GET /api/trc/attachments?…` | `RECORDS` |
| A1 | `TRC_DASHBOARD` | `get_trc_summary` ‖ `get_trc_metric_breakdown(TREND)` ‖ `(DISPOSITION)` ‖ `(COMPONENT)` ‖ `(FACILITY)` | `GET /api/trc/summary` · `GET /api/trc/metrics/{dimension}` | `KPI_SUMMARY` + `METRIC_BREAKDOWN`×4 |
| A6 | `ACTION_EXPORT` | `request_worklist_export` (confirm) | `POST /api/trc/exports` | `ACTION_RESULT` (link) |
| A7 | `VALIDATION_RUN` | `validate_claims([member])` | `POST /api/trc/validation/claims` | `VALIDATION_RUN` |
| A8 | `MRAT_STATUS` | `get_mrat_review_status` | `GET /api/trc/closure/{id}` | `MRAT_STATUS` |
| A9 | `ACTION_RESEND_NOTIFICATION` | `send_provider_notification` (confirm) | `POST /api/trc/notifications` | `ACTION_RESULT` |
| A10 | `ACTION_ESCALATE` | `escalate_to_provider_manager` (confirm) | `POST /api/trc/escalations` | `ACTION_RESULT` |
| A11 | `MEMBER_AUDIT_TRAIL` | `get_member_audit_trail` | `GET /api/trc/audit/{id}` | `MEMBER_SECTION` |
| A12 | `ACTION_LOG_INTERVENTION` | `log_intervention_activity` (confirm) | `POST /api/trc/interventions/{id}/activities` | `ACTION_RESULT` |
| A13 | `ACTION_BULK_RESEND` | `list_provider_outreach(provider_response=NON_RESPONSIVE)` → show list → `resend_notifications_bulk(explicit ids)` (confirm) | `GET /api/trc/notifications?response=` → `POST /api/trc/notifications/bulk-resend` | `NOTIFICATIONS` → `ACTION_RESULT` |
| A14 | `MEDICAL_RECORDS` | `get_attachment_access_link` | `POST /api/trc/attachments/{id}/access-link` | `RECORD_LINK` |
| A16 | `ACTION_SOFT_CLOSE` | `update_review_status(SOFT_CLOSED)` (confirm) | `POST /api/trc/closure` | `ACTION_RESULT` |

The full 29-tool catalog (generated from the live server: inputs, route, source, class) is in [`TOOL_CATALOG.md`](TOOL_CATALOG.md).
