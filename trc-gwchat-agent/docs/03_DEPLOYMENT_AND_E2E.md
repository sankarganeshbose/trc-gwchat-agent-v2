# 3 · Deployment, Gateway/MCP configuration, end-to-end execution, assumptions register

> Everything marked **ASSUMPTION / VERIFY** is not confirmed by the three source artifacts or by enterprise facts I could see. Each is isolated behind config so it can change without redesign.

## 3.1 Deployables and where things run

| # | Deployable | AgentCore protocol | Port / path | Image |
|---|---|---|---|---|
| 1 | **TRC GWChat Agent** (`trc_agent`, Strands) | HTTP (`BedrockAgentCoreApp`, `@app.entrypoint`) | 8080 `/invocations`, `/ping` | `Dockerfile.agent` |
| 2 | **TRC FastMCP server** (`trc_mcp`) | MCP (stateless streamable HTTP) | 8000 `/mcp` | `Dockerfile.mcp` |
| 3 | AgentCore **Gateway** (managed) | MCP front door | — | none |
| 4 | On-prem TRC REST API (GuideWell) | — | — | existing |

Both images are `python:3.12-slim`, built `linux/arm64` (VERIFY: current AgentCore Runtime requirement), launched through `opentelemetry-instrument` so traces/metrics land in AgentCore Observability / CloudWatch.

Hard constraints honoured: **no S3, RDS, OpenSearch, vector store, or AgentCore Memory**. The agent is stateless per request; confirmation tickets are HMAC-signed (no server-side store); idempotency state lives on-prem (the system of record). Nothing clinical is written anywhere in AWS except PHI-safe hashed identifiers in logs.

## 3.2 Network topology and the Option A / Option B decision

```
GWChat (browser/app)
   │ HTTPS + Entra ID JWT
   ▼
AgentCore Runtime  ── Agent (HTTP)          [AWS, VPC mode]
   │ MCP / HTTPS + user JWT (propagated)
   ▼
AgentCore Gateway  ── inbound JWT authorizer (+ optional Cedar policy)
   │ MCP target  (OAuth 2LO, or IAM SigV4 when target is a Runtime)
   ▼
FastMCP server                             [Option A: AgentCore Runtime in VPC | Option B: on-prem]
   │ HTTPS, OAuth client-credentials, X-On-Behalf-Of, X-Correlation-Id, Idempotency-Key
   ▼  Direct Connect / Site-to-Site VPN, private CA
On-prem TRC REST API → CareNavi / ADT-HIE / Provider Vista / EIP / Content Central / Claims / MRAT
```

**Why this is a decision.** The Gateway documentation I reviewed describes MCP-server targets reached by URL with OAuth or IAM auth; it does **not** document private (VPC) connectivity from the Gateway to a target. Therefore:

| | **Option A (recommended)** — FastMCP on AgentCore Runtime (MCP protocol) in AWS, VPC-attached to on-prem | **Option B** — FastMCP hosted on-prem, registered as a public/URL MCP target |
|---|---|---|
| Gateway → MCP | Registered as a Runtime target (IAM SigV4 / OAuth) – stays inside AWS | Requires an internet-reachable (or otherwise Gateway-reachable) on-prem endpoint |
| MCP → on-prem API | Private: VPC → Direct Connect/VPN | Local network |
| Security surface | No inbound hole into the data centre | New inbound path to DMZ; mTLS/WAF/IP allow-listing needed |
| Data residency | Only tool-result JSON transits AWS (already true in any option, because the agent receives it) | Same |
| Ops | Same CI/CD and observability as agent | Run/patch a service on-prem |

Either way the code is identical — only the Gateway target registration and `TRC_MCP_ONPREM_BASE_URL` change. **Open decision for GuideWell security/network.**

## 3.3 Where auth, authorization, network and secrets live

| Concern | Where it lives | Mechanism | Status |
|---|---|---|---|
| End-user authentication | GWChat → Runtime | Entra ID JWT validated by the Runtime **CUSTOM_JWT inbound authorizer** (discovery URL, allowed audience/clients) | ASSUMPTION: Entra is the IdP |
| Token reaching the agent | Runtime request-header allow-list | `Authorization` must be allow-listed so `context.request_headers` exposes it | VERIFY |
| Caller → Gateway | Gateway inbound authorizer | Agent propagates the user JWT (`TRC_AGENT_GATEWAY_AUTH=propagate`) or uses client-credentials (`client_credentials`) | Both implemented |
| Tool-level authorization (coarse) | Gateway | Optional AgentCore Policy / Cedar: which principals may call which `target___tool` | VERIFY syntax; config only |
| Tool-level authorization (fine) | **FastMCP** `run_tool` | Scopes `trc.read`, `trc.write`, `trc.records.read` checked per tool before any upstream call | Implemented + tested |
| Business authorization (who may see which member) | **On-prem API** | `X-On-Behalf-Of` carries the user id; on-prem remains the authority | ASSUMPTION: on-prem honours header |
| Write governance | Three independent gates | (1) agent `write_actions_enabled`, (2) human confirmation ticket, (3) MCP `write_tools_enabled` + `trc.write` scope | Implemented |
| Gateway → MCP target | Gateway target config | OAuth 2LO via AgentCore Identity credential provider, or IAM SigV4 for a Runtime target | Config |
| User identity at MCP server | Gateway/MCP | Forwarded JWT claims (`trust_upstream_jwt`) or allow-listed `x-gw-user-id` header. **No JWT signature re-verification in MCP today** (trusts the Gateway) | Hardening item H1 |
| MCP → on-prem | `clients/http.py` | OAuth2 client credentials (token cached), TLS with private CA bundle | ASSUMPTION |
| Secrets | AWS Secrets Manager / AgentCore Identity → env at start-up | `TRC_AGENT_TICKET_SECRET`, `TRC_MCP_CLIENT_SECRET`, log salts. Never in image or repo | Config |
| Network | VPC config on Runtime(s); SG egress to on-prem CIDR only; Gateway has no on-prem path | Direct Connect/VPN | Decision §3.2 |
| Config | Env vars with `TRC_AGENT_` / `TRC_MCP_` prefix (pydantic-settings); route overrides via `TRC_MCP_ENDPOINT_OVERRIDES_JSON` | See `.env.example` | Implemented |
| Audit | On-prem audit log (authoritative) + structured logs with one correlation id | `X-Correlation-Id` end-to-end | Implemented |

## 3.4 AgentCore Runtime deployment notes

1. Build and push both images to ECR (`docker buildx build --platform linux/arm64 …`).
2. **Agent runtime** — HTTP protocol; execution role needs `bedrock:InvokeModel*` (the chosen inference profile), the Gateway invoke permission if using SigV4, `secretsmanager:GetSecretValue` for its secrets, CloudWatch/X-Ray write. VPC mode only if the Gateway URL is private; otherwise public egress to Gateway and Bedrock.
3. **MCP runtime (Option A)** — MCP protocol; stateless server on `0.0.0.0:8000/mcp`; VPC-attached to a subnet routed to on-prem; role needs only Secrets Manager + logs. Register it as a Gateway target.
4. **Sessions.** Runtime provides a session id per conversation (`X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`); the agent uses it only to bind confirmation tickets. No conversation history is stored; GWChat resends the context it needs.
5. **Scaling / timeouts.** One new `Agent` per request keeps requests isolated; the nested timeout budget (§2.2) must fit under the Runtime request limit (VERIFY current limits).
6. **Model.** `TRC_AGENT_MODEL_ID` default is a placeholder inference-profile id (VERIFY availability in the chosen region). Temperature 0. Optional `TRC_AGENT_GUARDRAIL_ID`.
7. **Rollout.** Start with `TRC_MCP_BACKEND=stub` in dev, `http` in test against a non-prod on-prem API, keep both write flags `false` until governance sign-off; flip the MCP flag first in a controlled environment.
8. **Observability.** Dashboards on: tool latency/err by `code`, `UPSTREAM_SCHEMA_MISMATCH` count (contract drift alarm), ledger-grounding violations, `NEEDS_CONFIRMATION` → executed ratio, circuit-breaker opens.

## 3.5 Gateway / MCP configuration assumptions

All VERIFY against the current AgentCore Gateway console/API at implementation time.

| Item | Assumption |
|---|---|
| Target type | **MCP server target**, one target named `trc` (so tools surface as `trc___get_member_details`; the agent canonicalises by stripping `___`) |
| Endpoint | Option A: Runtime ARN/URL of the MCP runtime; Option B: HTTPS URL of the on-prem server |
| Outbound auth | OAuth 2LO (client-credentials) via AgentCore Identity, or IAM SigV4 for a Runtime target |
| Inbound auth | CUSTOM_JWT (same Entra issuer as Runtime) with audience for GWChat agent |
| Tool discovery | Gateway lists tools from `tools/list`; re-sync required after deploying a tool change. `docs/TOOL_CATALOG.md` is the source for review |
| Tool exposure | Expose all 29; the agent allow-list (`policy.ALLOWED_MCP_TOOLS`) is a second, independent filter. Write tools can be withheld at the Gateway/Policy in early environments |
| Identity propagation | Gateway forwards the caller's identity so the MCP server can see the user (JWT claims or `x-gw-user-id`). **If it does not**, MCP falls back to a service principal and on-prem loses per-user authorization → blocker for writes |
| Scopes | `trc.read` for read tools; `trc.records.read` for attachments; `trc.write` for the six write tools |
| Payload limits | Largest response is the worklist page (bounded `limit`) and the member-record fan-out (13 calls); no document bytes |

## 3.6 End-to-end execution examples

Real output of `python -m tests.integration.demo_trace`: scripted LLM decisions, but **real** FastMCP server over streamable HTTP, **real** MCP client, real agent hooks/ledger/blocks, and the stateful stub standing in for on-prem. Times are ms from the start of the request. In production the hop `Agent → MCP` goes through the Gateway (`target___tool`).

### Example 1 — single tool: "Show me the TRC status for member HCC-4471829"

```
GWChat → Agent          "Show me the TRC status for member HCC-4471829"
  Gateway/MCP tools/call  get_member_trc_status → FastMCP → on-prem GET /api/trc/members/HCC-4471829/status   [505ms → 555ms]
Agent → GWChat          status=OK intent=MEMBER_TRC_STATUS blocks=['MEMBER_SECTION'] gaps=0 pending=0
                        "HCC-4471829 is at Provider Notified; the fax alert is PENDING and no Provider Vista upload is on file."
```

### Example 2 — parallel fan-out plus a dependency: "Open the TRC record for Dorothy Simmons (HCC-4471829)"

```
GWChat → Agent          "Open the TRC record for Dorothy Simmons (HCC-4471829)"
  wave 1 (concurrent, bounded at 6):
    get_member_details · get_member_trc_status · get_validation_evidence · get_member_adt_timeline
    get_discharge_summary · get_discharge_medications            [820ms → 938ms]
  wave 2:
    get_followup_status · get_risk_assessment · get_intervention_status · get_prior_admissions
    get_provider_outreach · get_attachments                      [1065ms → 1184ms]
  dependent step (needs provider_id from outreach):
    get_provider_contacts → on-prem GET /api/trc/provider/PRV-1000   [1358ms → 1409ms]
Agent → GWChat          status=OK intent=MEMBER_TRC_RECORD blocks=['MEMBER_RECORD'] gaps=0
                        "Record loaded for HCC-4471829. Provider alert PENDING; no upload; HIGH risk."
```

### Example 3 — write path with human confirmation and idempotent replay

```
3a GWChat → Agent   "Resend the failed provider alert for HCC-2231087"
   LLM calls send_provider_notification → hook CANCELS it, signs a ticket (user+session+tool+args+expiry)
   Agent → GWChat   status=NEEDS_CONFIRMATION, pending_actions=[ticket, summary, args, expires_at]
                    (nothing was sent to on-prem)

3b GWChat → Agent   {confirmation:{ticket, decision:"approve"}}          ← no LLM in this turn
   Agent verifies signature/expiry/user/session → tools/call send_provider_notification
        → FastMCP (write gates + scope) → on-prem POST /api/trc/notifications  Idempotency-Key = tk-<sha256(ticket)>
   Agent → GWChat   status=OK, ACTION_RESULT
                    "Alert resent for HCC-2231087 via FAX — status SENT (notification NTF-100201); Proxy Task updated: True."

3c Double-click: same confirmation again → same idempotency key → on-prem returns original result
   Agent → GWChat   "... (this request had already been processed — no duplicate was created)."
```

### Example 4 — graceful degradation (covered by `tests/integration/test_agent_e2e.py`)

When a tool is unavailable, the block is omitted, a `data_gaps` entry carries the code, and the status becomes `PARTIAL`/`UNAVAILABLE`. The narrative never states the missing information; if it tried to cite an id absent from evidence, the grounding check swaps in the deterministic summary.

## 3.7 Test evidence

`python -m pytest tests -q` → **104 passed**. Coverage by layer:

| Layer | What is proven |
|---|---|
| Contract | Every tool has an output schema; annotations match `policy.py` classification; `MRAT_CLOSED` is not a legal argument |
| Read tools | All 21 reads + 2 computes return valid envelopes; **fixture sweep** runs every member-scoped tool over all 10 prototype members (incl. excluded/N-A cases) |
| Write tools | Resend only for FAILED/PENDING; soft-close only from VALIDATION_PASSED; bulk cap; idempotent replay; write flag gate |
| Security/faults | Missing scope → FORBIDDEN; timeout/5xx/schema drift → typed failures; no upstream body leakage |
| HTTP client | respx: retries only on GET or POST+key, header set, path quoting, circuit breaker, endpoint overrides |
| Agent | Ticket tamper/expiry/user/session binding; hook allow-list/budget/id validation/write interception; DAG ordering; grounding; request validation |
| E2E | 8 scenarios over a live HTTP FastMCP server |

Known cosmetic: an asyncio "Task was destroyed but it is pending" / unclosed-resource warning on MCP client teardown in integration tests. It does not affect results; production uses per-request connector lifecycle (follow-up L2).

## 3.8 Assumptions and open-items register

| # | Item | Why it matters | Isolated in |
|---|---|---|---|
| A1 | On-prem endpoint paths/verbs (`DEFAULT_ROUTES`) are placeholders | Real contract unknown | `clients/base.py` + env overrides |
| A2 | On-prem JSON field names (camelCase fixture shape derived from the prototype) | Mapping | `adapters/mappers.py` |
| A3 | MCP → on-prem uses OAuth2 client-credentials + `X-On-Behalf-Of` | Per-user authz on-prem | `clients/http.py` |
| A4 | Entra ID is the IdP; Runtime CUSTOM_JWT; Gateway inbound JWT | Authn | Deployment config |
| A5 | Gateway forwards user identity to the MCP target | Per-user audit, write safety | `security.py` |
| A6 | Gateway cannot reach on-prem privately → Option A vs B | Network design | Deployment |
| A7 | `update_review_status` = confirmation-gated **soft close**; deck wording ("syncs status back to GWChat") is ambiguous | Semantics | `tools/closure.py`, `ReviewStatusTarget` |
| A8 | Final MRAT closure is human-only; no tool can set it | HEDIS governance | contract |
| A9 | Per-member **medication reconciliation** status and separate **TCM eligibility** (baseline docx) are not in the prototype → no tool; the agent states "unavailable" | Gap vs docx | Add `Op` + tool when API exists |
| A10 | `discharge_id` optional; one active discharge per member assumed | Multi-admission members | tool args + mapper |
| A11 | Escalation target, resend channel selection, bulk cap (25) are prototype-derived | Business rules | tools + on-prem |
| A12 | Risk tiers HIGH >20%, MEDIUM 10–20%, LOW <10% from prototype | Display only | contracts |
| A13 | Aggregate dashboard figures (1,284 discharges etc.) come from the prototype; period labels are on-prem's | Stub realism | stub |
| A14 | arm64 container + the Bedrock model id/inference profile + AgentCore header names/limits | Deploy | Dockerfiles, env |
| A15 | Write-action governance (who may approve, audit retention) not defined by sources | Go-live gate | flags (default off) |
| A16 | "Last 3/10/14 days" prototype inconsistency → `lookback_days` parameter | Filters | worklist tools |

## 3.9 Hardening backlog (before production)

- **H1** Verify the user JWT at the MCP server (JWKS, issuer, audience, expiry) instead of trusting the Gateway.
- **H2** Pass a signed confirmation attestation (ticket) to the MCP server so it can independently refuse writes lacking human approval.
- **H3** Wire the real on-prem API: set `TRC_MCP_BACKEND=http`, overrides/mappers, contract tests against a sandbox.
- **H4** Gateway/Policy (Cedar) rules per tool and role; confirm identity propagation.
- **H5** Load/chaos testing of the fan-out (13 calls) against on-prem rate limits.
- **L1** Replace the stylistic ruff leftovers (7). **L2** Clean MCP client teardown in tests/connector.

## 3.10 Sources

- AgentCore Gateway MCP server targets: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html
- AgentCore Runtime MCP protocol: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html
