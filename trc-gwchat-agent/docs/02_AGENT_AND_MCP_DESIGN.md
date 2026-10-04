# 2 · Strands agent design, FastMCP architecture, project structure, code map

## 2.1 The central rule

| Layer | Owns | Never does |
|---|---|---|
| **Strands agent (LLM)** | Understanding the request, choosing tools, issuing independent calls together, writing ≤120 words of narrative | Fabricate data · call on-prem · execute writes · change tables · decide eligibility/validation/closure |
| **Agent deterministic code** | Input validation, allow-list, call budget, write confirmation, retries/timeouts, evidence ledger, block assembly, data gaps, grounding check, confirmed-action execution | Interpret language |
| **AgentCore Gateway** | Authn/z of the caller, tool exposure/policy, routing to the MCP target | Hold data |
| **FastMCP tools** | Typed contracts, validation, scope checks, idempotency, response normalisation, fail-closed mapping, PHI-safe logs | Reason, summarise, infer |
| **On-prem APIs** | Business rules and data (eligibility, 3-day validation, resend states, transitions, audit) | — |

## 2.2 Strands agent design (Step 2)

**Per-request construction** (`agent.py::_run_llm_turn`): a *new* `Agent` per request (request-scoped state) with `BedrockModel` (temperature 0, optional Bedrock Guardrail), the allow-list-filtered MCP tools from the Gateway, two local composite tools, `ToolPolicyHook`, and `ConcurrentToolExecutor` so all `tool_use` blocks emitted in one model step run in parallel.

| Concern | Design (file) |
|---|---|
| Responsibilities | §1.1 |
| System prompt | `prompts/trc_system_prompt.py` — Technical-Design rules 1-10 + scope, MRAT, injection, brevity. User turn is split into trusted `<request_context>` (UI state) and untrusted `<user_message>`. |
| Tool registration | `orchestration/gateway.py` opens an MCP session to the Gateway, `list_tools`, then keeps only names in `policy.ALLOWED_MCP_TOOLS` (Gateway names `target___tool` are canonicalised). Anything else is invisible to the LLM *and* blocked again by the hook. |
| Tool selection | LLM, guided by rich tool descriptions ("Use for…", "Does NOT…"). Composite tools exist for the two heavy flows so the model doesn't plan 13 calls. |
| Input validation | `GWChatRequest` (pydantic, `extra=forbid`, 4,000-char cap, id regexes, exactly one of `message`/`confirmation`) → hook re-validates every `member_id(s)` the LLM emits → MCP re-validates with the same patterns. |
| Context/state | No conversation memory. GWChat supplies `context.selected_member_id` (resolves "this member") and `active_filters`. Tool results live only in the per-turn **ledger**. |
| Multi-tool orchestration | LLM-driven parallel fan-out + `orchestration/workflow.py` DAG executor (`Step`, `after=`, bounded concurrency, skip-on-failed-dependency). |
| Sequential vs parallel | Table below. |
| Error handling | Tools never raise for expected failures — they return `Envelope{ok:false,error{code,retryable}}`. Agent maps failures to `data_gaps`; status becomes `PARTIAL`/`UNAVAILABLE`. Malformed tool output → `UPSTREAM_SCHEMA_MISMATCH` (fail closed). Timeouts/transport errors → retryable gaps. |
| Retry | Reads/compute: Strands `AfterToolCallEvent.retry` once for `UPSTREAM_TIMEOUT/UNAVAILABLE/RATE_LIMITED`; playbooks use `ResilientCaller` (exp. backoff + jitter, bounded). Writes are **never** auto-retried by the LLM loop; the confirmed executor may retry only with the ticket-derived idempotency key. MCP server adds its own bounded retries + circuit breaker toward on-prem. |
| Timeouts | Nested budget: on-prem 5 s/attempt (GET) · 10 s (POST), ≤2 retries ⇒ ≲17 s < agent tool 20 s (writes 30 s) < turn 90 s. Gateway connect 10 s. A turn timeout returns `ERROR` with "no data was inferred". |
| Response aggregation | `services/blocks.py`: ledger → typed `Block`s (verbatim tool `data`, `source_systems`, `as_of`), `data_gaps`, `tool_trace` (no payloads), deterministic `intent` and `status`. |
| Guardrails | Allow-list · call budget (24) · id validation · **write interception** · no LLM-chosen idempotency keys · scope-limited prompt · injection stance (tool text is data) · optional Bedrock Guardrail · **grounding check** on the narrative. |
| Structured response | `GWChatResponse` (`models/schemas.py`): `status` ∈ OK / PARTIAL / UNAVAILABLE / NEEDS_CONFIRMATION / NARRATIVE_ONLY / ERROR. |
| Observability | structlog JSON with PHI-safe hashed refs; OTEL via `opentelemetry-instrument` (AgentCore Observability); one correlation id (`request_id`) sent as `X-Correlation-Id` end-to-end; Strands `trace_attributes`. |

**Sequential vs parallel**

| Flow | Plan |
|---|---|
| Dashboard (P1/A1) | all independent → one parallel step |
| Member record (P3) | layer 1: 12 reads in parallel (bounded by `max_parallel_calls=6` → two waves); layer 2: `get_provider_contacts` needs `provider_id` from `get_provider_outreach` → **sequential dependency** |
| Validate + board (P5) | `validate_claims` **first** (board/summary must reflect the run) → `get_closure_board` ‖ `get_validation_summary` |
| Bulk resend (A13) | list (read) → human reviews list → one confirmed write with explicit ids |
| Resend/escalate/soft-close/log/export | single write after confirmation |

**Deterministic vs LLM decisions**

| LLM | Deterministic code |
|---|---|
| Which tools, which filters from natural language | Whether a tool is allowed, ids valid, budget left |
| Parallel fan-out in a model step | Dependency order in playbooks |
| ≤120-word narrative | Blocks, counts, statuses, intent label, gaps, trace |
| Asking for a missing member id | Whether a write may run (**never** without a valid ticket) |
| — | Grounding verdict; fallback summary when narrative is ungrounded |

**Write path (human-in-the-loop, stateless)**

1. LLM calls e.g. `send_provider_notification`. `ToolPolicyHook.before` **cancels** the call (`cancel_tool`) and issues an HMAC ticket binding *user + session + tool + exact args + expiry* (`services/confirmation.py`). The LLM is told the action is queued.
2. Response: `status=NEEDS_CONFIRMATION`, `pending_actions[{ticket, summary, arguments, expires_at}]`. The summary is generated deterministically from the arguments.
3. User clicks Approve → GWChat sends `{confirmation:{ticket, decision}}`. The agent verifies signature/expiry/user/session and executes **that exact call** with idempotency key = `tk-` + SHA-256(ticket) — no LLM involved. A double-click replays the same key; on-prem returns the original result (`idempotent_replay=true`).
4. The result message is generated from the tool envelope, never by the model. Failure ⇒ "NOT completed (CODE)".

**Grounding check** (`services/grounding.py`): any `HCC-/PRV-/NTF-/ESC-/TRN-/…` identifier in the narrative must appear in tool evidence, the user's own message, or a queued action; completion claims ("has been sent/closed…") are rejected unless an executed action succeeded. Violation ⇒ narrative replaced by a deterministic summary and a warning is attached; blocks are untouched.

## 2.3 FastMCP architecture (Step 3-4)

```
tool function (typed args via Annotated/Pydantic)            tools/*.py
   └─ run_tool(): principal → scope check → [precheck] → idempotency key → client.call(Op, path/query/body)
        └─ OnPremClient (Protocol)  ── HttpOnPremClient | StubOnPremClient          clients/
              HTTP: OAuth2 token · TLS/private CA · per-method timeouts · bounded retry+jitter · circuit breaker · identity headers
        └─ mappers.<op>(raw JSON) → Pydantic contract                              adapters/mappers.py
   └─ Envelope[T](ok, data|error, meta)  — validation failure ⇒ UPSTREAM_SCHEMA_MISMATCH (no payload echo)
```

* **Granularity.** 21 read tools, 2 compute tools (`validate_claims`, `get_attachment_access_link`), 6 write tools. Each maps to one on-prem operation (`Op`), one source system and one response model.
* **Contract.** Every tool returns `Envelope[T]` with an `outputSchema`; `meta` carries `request_id`, `tool`, `source_system`, `as_of`, `latency_ms`, `idempotency_key`, `read_only`. Error codes: INVALID_ARGUMENT, UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, CONFLICT, PRECONDITION_FAILED, RATE_LIMITED, UPSTREAM_TIMEOUT, UPSTREAM_UNAVAILABLE, UPSTREAM_ERROR, UPSTREAM_SCHEMA_MISMATCH, INTERNAL. Upstream bodies and exception text are never forwarded.
* **Auth expectations.** Scopes `trc.read`, `trc.write`, `trc.records.read` (records access is separately governed). Writes additionally need `TRC_MCP_WRITE_TOOLS_ENABLED=true`. Identity from token claims or an allow-listed header (ASSUMPTION, §3 doc 3).
* **Idempotency.** Writes always carry a key: ticket-derived (agent) or auto-derived (10-min bucket of user+tool+payload). `Idempotency-Key` header to on-prem; the HTTP client only retries POSTs that have one.
* **Classification.** MCP `annotations` (`readOnlyHint`, `idempotentHint`, `destructiveHint=false`) + tags `read|compute|write`; the agent's `policy.py` mirrors this and a contract test fails if they drift.
* **Isolation of API assumptions.** Routes: `clients/base.py::DEFAULT_ROUTES` + env overrides. Field names: `adapters/mappers.py`. Auth/TLS/retry: `clients/http.py`. Nothing in `tools/` or the agent knows an URL or JSON field of the on-prem API.

## 2.4 Project structure (as built)

```
trc-gwchat-agent/
├── pyproject.toml · requirements*.txt · Dockerfile.agent · Dockerfile.mcp · .env.example
├── docs/                         01_…ANALYSIS · 02_…DESIGN (this) · 03_…DEPLOYMENT · TOOL_CATALOG (generated)
├── scripts/                      build_fixtures.py (prototype → stub data) · gen_tool_catalog.py
├── src/
│   ├── trc_contracts/            common.py (Envelope, errors, enums) · domain.py (29 payload models)
│   ├── trc_mcp/                  FastMCP server (deployable #2)
│   │   ├── server.py config.py deps.py security.py errors.py logging.py
│   │   ├── tools/                cohort · member · discharge · provider · notification · validation · records · closure
│   │   ├── clients/              base.py (Op, routes, Protocol) · http.py · stub.py · fixtures/members.json
│   │   └── adapters/mappers.py   on-prem DTO → contract
│   └── trc_agent/                Strands agent (deployable #1)
│       ├── main.py               AgentCore Runtime entrypoint (BedrockAgentCoreApp)
│       ├── agent.py              TrcAgentService: LLM turn · confirmed execution · assembly
│       ├── config.py policy.py logging.py
│       ├── prompts/trc_system_prompt.py
│       ├── models/schemas.py     GWChat request/response
│       ├── orchestration/        gateway.py · caller.py · workflow.py (DAG) · local_tools.py (composites)
│       └── services/             hooks.py · confirmation.py · ledger.py · blocks.py · grounding.py
└── tests/                        mcp/ (contract, read, write, security/faults, http client, fixture sweep) · agent/ · integration/ (real MCP/HTTP e2e + demo_trace)
```

## 2.5 Code map — where each requested artifact lives

| Requested | File(s) |
|---|---|
| Strands agent | `trc_agent/agent.py`, `orchestration/*`, `services/hooks.py` |
| FastMCP server | `trc_mcp/server.py` |
| MCP tools | `trc_mcp/tools/*.py` (29) |
| API client abstraction | `trc_mcp/clients/base.py` (+ `http.py`, `stub.py`), `adapters/mappers.py` |
| Pydantic models | `trc_contracts/*`, `trc_agent/models/schemas.py` |
| Configuration | `trc_mcp/config.py`, `trc_agent/config.py`, `.env.example` |
| Error handling | `trc_mcp/errors.py`, `deps.run_tool`, `clients/http.py`, agent hooks/ledger |
| Logging | `trc_mcp/logging.py`, `trc_agent/logging.py` (hashed PHI refs) |
| Unit/integration tests | `tests/**` (104 tests) |
