# GWChat TRC Integration Agent

**GWChat → Agent (AgentCore Runtime, Strands) → AgentCore Gateway → FastMCP tools → on-prem REST API → GuideWell systems**

Clinical/member data stays on-prem. There is no S3, RDS, OpenSearch or vector store. The agent never calls on-prem APIs directly; it only calls MCP tools through the Gateway. Writes require a human confirmation click.

| Doc | Content |
|---|---|
| `docs/01_ARCHITECTURE_AND_PROTOTYPE_ANALYSIS.md` | Architecture, prompt inventory, Prompt → Intent → Tool → API mapping |
| `docs/02_AGENT_AND_MCP_DESIGN.md` | Strands design, FastMCP architecture, structure, code map |
| `docs/03_DEPLOYMENT_AND_E2E.md` | Deployment model, auth/network/secrets, E2E examples, assumptions register |
| `docs/TOOL_CATALOG.md` | The 29 MCP tools (generated) |

> **Read this first.** Anything marked **VERIFY** depends on AWS console/CLI behaviour or GuideWell facts I could not confirm. AWS tooling changes quickly: where a command below differs from `agentcore --help` or the console, trust the tool. The on-prem API is **stubbed** (`TRC_MCP_BACKEND=stub`); real endpoints and field names are placeholders (see Part 4).

---

## Contents

- Part 0 – What gets deployed
- Part 1 – Local setup (no AWS needed for steps 1–5)
- Part 2 – Run locally against real Bedrock (optional)
- Part 3 – Deploy to AWS step by step
- Part 4 – Wiring the real on-prem API
- Part 5 – Go-live checklist
- Part 6 – Troubleshooting
- Reference – environment variables, repo layout

---

## Part 0 – What gets deployed

| # | Component | Where it runs | Protocol | Port | Image |
|---|---|---|---|---|---|
| 1 | **Agent** (`trc_agent`) | AgentCore Runtime | HTTP (`/invocations`, `/ping`) | 8080 | `Dockerfile.agent` |
| 2 | **FastMCP server** (`trc_mcp`) | AgentCore Runtime (MCP protocol) – Option A; or on-prem – Option B | Streamable HTTP `/mcp` | 8000 | `Dockerfile.mcp` |
| 3 | **Gateway** | AgentCore Gateway (managed) | MCP | – | none |
| 4 | **On-prem TRC REST API** | GuideWell data center | HTTPS | – | existing |

Option A vs B (where the MCP server lives) is explained in `docs/03_DEPLOYMENT_AND_E2E.md` §3.2. **Option A is assumed below** because the Gateway docs I reviewed don't describe private connectivity to MCP targets.

---

## Part 1 – Local setup

### 1.1 Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11+ (3.12 recommended, matches the images) | `python3 --version` |
| Git, curl | any | – |
| Docker (with buildx) | needed only for Part 3 | `docker buildx version` |
| AWS CLI v2 | needed only for Parts 2–3 | `aws --version` |

### 1.2 Create the environment

```bash
cd trc-gwchat-agent
python3.12 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt      # agent + MCP + test tooling (pinned)
pip install -e .                     # installs trc_contracts, trc_mcp, trc_agent from src/
```

Pinned versions (see `requirements*.txt`): strands-agents 1.57.2, bedrock-agentcore 1.24.0, mcp 1.30.0, fastmcp 3.4.7, pydantic 2.13.5, httpx 0.28.1, structlog 26.1.0.

### 1.3 Configure

```bash
cp .env.example .env
```

Both services read `.env` (prefixes `TRC_MCP_` and `TRC_AGENT_`). For local work edit these lines:

```dotenv
TRC_MCP_BACKEND=stub                 # in-memory fake on-prem, seeded from the prototype's 10 members
TRC_MCP_REQUIRE_AUTH=false           # local only: no JWT, runs as "dev-user" with all scopes
TRC_MCP_WRITE_TOOLS_ENABLED=true     # local only: so you can try the write flow against the stub
TRC_AGENT_WRITE_ACTIONS_ENABLED=true # local only
TRC_AGENT_GATEWAY_URL=http://localhost:8000/mcp   # point the agent straight at the MCP server (no Gateway locally)
TRC_AGENT_GATEWAY_AUTH=none
TRC_AGENT_REGION=us-east-1
TRC_AGENT_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0   # VERIFY: a model/inference profile enabled in your account
TRC_AGENT_TICKET_SECRET=local-dev-secret-at-least-32-characters-long
```

Never use `REQUIRE_AUTH=false` or the default ticket secret outside your laptop.

### 1.4 Run the tests (no AWS credentials, no network)

```bash
python -m pytest tests -q
# expected: 104 passed
```

What this proves: tool contracts, every tool across all 10 prototype members, write-rule enforcement, security/fault handling, the HTTP client (mocked), agent guardrails, and 8 end-to-end scenarios over a **real** FastMCP HTTP server with a scripted stand-in for the LLM. You may see a harmless "Task was destroyed but it is pending" warning from MCP client teardown.

### 1.5 See an end-to-end trace (still no AWS)

```bash
python -m tests.integration.demo_trace
```

Prints GWChat → Agent → MCP tool calls → stub on-prem → response for: a single tool call, a 13-call parallel fan-out with one dependent step, and a write proposal → approve → idempotent replay.

### 1.6 Start the MCP server and call a tool yourself

```bash
python -m trc_mcp.server              # serves http://localhost:8000/mcp (stateless streamable HTTP)
```

In another terminal, list the tools and call one with the FastMCP client:

```bash
python - <<'PY'
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://localhost:8000/mcp") as c:
        tools = await c.list_tools()
        print(len(tools), "tools")                      # 29 (write tools are listed; they're gated at call time)
        r = await c.call_tool("get_member_trc_status", {"member_id": "HCC-4471829"})
        print(r.structured_content)                     # Envelope: {ok, data, error, meta}

asyncio.run(main())
PY
```

Regenerate the tool catalog any time: `python scripts/gen_tool_catalog.py`.

---

## Part 2 – Run the real agent locally (optional; needs AWS credentials for Bedrock)

This uses a real LLM but the stub on-prem API, so **no member data is involved** (the stub holds synthetic prototype data).

1. Enable model access: Bedrock console → *Model access* → request the Claude model you set in `TRC_AGENT_MODEL_ID`. **VERIFY** the exact inference-profile ID in your region (Bedrock console → *Inference profiles*).
2. Authenticate: `aws sso login` (or export `AWS_PROFILE`/keys). The caller needs `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on the profile.
3. Terminal A: `python -m trc_mcp.server`
4. Terminal B: `python -m trc_agent.main` (AgentCore app on `:8080`)
5. Terminal C, ask a question:

```bash
curl -s http://localhost:8080/invocations \
  -H 'Content-Type: application/json' \
  -d '{
        "session_id": "local-session-0001",
        "user_id": "dev-user",
        "message": "Show me the TRC status for member HCC-4471829",
        "context": {"selected_member_id": null, "active_filters": {}}
      }' | python -m json.tool
```

Response: `status`, `intent`, `message` (≤120 words, grounding-checked), `blocks` (verbatim tool data), `data_gaps`, `pending_actions`, `tool_trace`.

6. Try the write flow: ask `"Resend the failed provider alert for HCC-2231087"`. You get `status: NEEDS_CONFIRMATION` and a `pending_actions[0].ticket`. Nothing has been sent yet. Approve it:

```bash
curl -s http://localhost:8080/invocations -H 'Content-Type: application/json' -d '{
  "session_id": "local-session-0001", "user_id": "dev-user",
  "confirmation": {"ticket": "<paste ticket>", "decision": "approve"}
}' | python -m json.tool
```

Posting the same approval twice returns the original result with "no duplicate was created". The ticket is bound to `user_id` and `session_id`, so use the same values.

---

## Part 3 – Deploy to AWS, step by step

### Target architecture (Option A)

```
GWChat ──JWT──► Runtime: Agent ──JWT──► Gateway ──OAuth/SigV4──► Runtime: FastMCP ──VPC/DX/VPN──► On-prem API
```

### 3.0 Decisions and inputs you need first

| Needed | Why | Owner |
|---|---|---|
| AWS account + region where AgentCore Runtime/Gateway and your Claude model are available (**VERIFY**) | Everything | Cloud team |
| OIDC issuer for end users (assumed Entra ID): discovery URL, client IDs, audience | Runtime/Gateway inbound auth | Identity team |
| Network path from a VPC to the on-prem TRC API (Direct Connect/VPN), routes, DNS, private CA bundle | MCP → on-prem | Network team |
| On-prem API contract + a service principal (client id/secret, scope, token URL) | Part 4 | App team |
| Decision: Option A (MCP in AWS) vs B (MCP on-prem) | Where Part 3.5 points | Security |

### 3.1 AWS foundations

```bash
export AWS_REGION=us-east-1                 # VERIFY: your approved region
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_BASE=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

aws ecr create-repository --repository-name trc-agent --region $AWS_REGION
aws ecr create-repository --repository-name trc-mcp   --region $AWS_REGION
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_BASE
```

Create secrets (values never go in the repo or image):

```bash
aws secretsmanager create-secret --name trc/agent/ticket-secret   --secret-string "$(openssl rand -hex 32)"
aws secretsmanager create-secret --name trc/mcp/onprem-client     --secret-string '{"client_id":"<id>","client_secret":"<secret>"}'
aws secretsmanager create-secret --name trc/log-salt              --secret-string "$(openssl rand -hex 16)"
```

### 3.2 Network (Option A)

1. Create or reuse a VPC with private subnets reachable to on-prem (Direct Connect/VPN). Route the on-prem CIDR for the TRC API.
2. Security group for the MCP runtime: egress 443 only to the on-prem API CIDR (plus AWS endpoints it needs: Secrets Manager, CloudWatch Logs, ECR – use VPC endpoints if the subnets have no NAT).
3. Make the on-prem API hostname resolvable from the VPC (Route 53 Resolver outbound endpoint or private hosted zone).
4. Test reachability from an EC2/CloudShell-in-VPC host: `curl -v --cacert ca.pem https://<onprem-host>/health` (**VERIFY** the real health path).

### 3.3 IAM roles

Create two Runtime execution roles with the AgentCore Runtime service principal as trusted entity (**VERIFY** the trust policy from the AgentCore docs/console "create role" helper).

| Role | Permissions |
|---|---|
| `trc-agent-runtime-role` | `bedrock:InvokeModel*` on your inference profile and underlying model ARNs; `secretsmanager:GetSecretValue` on `trc/agent/*` and `trc/log-salt`; CloudWatch Logs + X-Ray write; ECR pull; Gateway invoke permission if you use SigV4 to the Gateway |
| `trc-mcp-runtime-role` | `secretsmanager:GetSecretValue` on `trc/mcp/*` and `trc/log-salt`; CloudWatch Logs + X-Ray write; ECR pull. **No Bedrock, no S3** |

### 3.4 Build and push the images (arm64)

```bash
docker buildx build --platform linux/arm64 -f Dockerfile.mcp   -t $ECR_BASE/trc-mcp:0.1.0   --push .
docker buildx build --platform linux/arm64 -f Dockerfile.agent -t $ECR_BASE/trc-agent:0.1.0 --push .
```

arm64 is assumed to be required by AgentCore Runtime (**VERIFY**). On an Intel machine, buildx uses QEMU emulation, so allow extra build time.

If your on-prem API uses a private CA, bake the CA bundle into the MCP image (or mount it) at the path in `TRC_MCP_CA_BUNDLE`. Don't commit it to the repo.

### 3.5 Deploy the MCP server as an AgentCore Runtime (MCP protocol)

**Console path (most reliable):** Bedrock AgentCore → *Runtime* → *Create agent runtime*.

| Field | Value |
|---|---|
| Name | `trc-mcp` |
| Container image | `$ECR_BASE/trc-mcp:0.1.0` |
| Protocol | **MCP** (stateless streamable HTTP on port 8000, path `/mcp`) |
| Execution role | `trc-mcp-runtime-role` |
| Network mode | **VPC** → the private subnets and security group from 3.2 |
| Inbound auth | IAM (SigV4) if the Gateway calls it with a service role; or JWT/OAuth if you register it as an OAuth target (**VERIFY** which options the Gateway offers for Runtime targets) |
| Environment | see below |

Environment variables for `trc-mcp`:

```dotenv
TRC_MCP_BACKEND=stub                      # FIRST deploy with stub to verify plumbing; switch to http in Part 4
TRC_MCP_REQUIRE_AUTH=true
TRC_MCP_TRUST_UPSTREAM_JWT=true           # until hardening item H1 (verify JWT in MCP) is done
TRC_MCP_WRITE_TOOLS_ENABLED=false
TRC_MCP_LOG_LEVEL=INFO
# Secrets: inject from Secrets Manager rather than typing values (TRC_MCP_CLIENT_ID, TRC_MCP_CLIENT_SECRET, TRC_MCP_LOG_SALT).
```

**CLI path (alternative):** the AgentCore starter toolkit (`pip install bedrock-agentcore-starter-toolkit`) can configure/launch, but check its current flags (**VERIFY**):

```bash
agentcore configure --help    # look for entrypoint, protocol (MCP), ecr, execution-role, vpc options
agentcore launch   --help
```

Smoke test (Runtime must allow your caller): after status is `READY`, invoke through the Gateway in 3.7 rather than directly. For a quick direct check, use the AgentCore invoke tooling with a `tools/list` call (**VERIFY** the current invoke syntax for MCP runtimes).

### 3.6 Create the Gateway and register the MCP target

Console: Bedrock AgentCore → *Gateways* → *Create gateway*.

1. **Name:** `trc-gateway`. **Protocol:** MCP.
2. **Inbound auth:** Custom JWT → discovery URL = your OIDC issuer's `.well-known/openid-configuration`; allowed audience/client = the GWChat agent client (**VERIFY** field names).
3. **Target:** *Add target* → type **MCP server** → name **`trc`** → endpoint = the `trc-mcp` Runtime (ARN/URL as the console asks).
   - Outbound auth: IAM SigV4 for a Runtime target, or OAuth client-credentials via an AgentCore Identity credential provider (**VERIFY**).
4. **Tool names:** the Gateway exposes them as `trc___get_member_details` etc. (`target___tool`). The agent strips the `trc___` prefix when matching its allow-list, so no code change is needed.
5. **Sync/list tools** and confirm all 29 appear. `docs/TOOL_CATALOG.md` is the expected list. Re-sync after every MCP tool change.
6. **Policy (optional but recommended before writes):** attach an AgentCore Policy (Cedar) so that only specific groups can call the six write tools (`send_provider_notification`, `resend_notifications_bulk`, `escalate_to_provider_manager`, `log_intervention_activity`, `update_review_status`, `request_worklist_export`). **VERIFY** policy syntax in the current docs.
7. Copy the **Gateway MCP URL**. It looks like `https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp`.

### 3.7 Deploy the agent as an AgentCore Runtime (HTTP protocol)

Console: *Runtime* → *Create agent runtime*.

| Field | Value |
|---|---|
| Name | `trc-agent` |
| Image | `$ECR_BASE/trc-agent:0.1.0` |
| Protocol | **HTTP** (port 8080: `/invocations`, `/ping`) |
| Role | `trc-agent-runtime-role` |
| Network | Public egress is fine if Gateway and Bedrock are reached over public AWS endpoints; use VPC mode + endpoints if your policy requires private only |
| Inbound auth | **Custom JWT** (same Entra issuer/audience as the Gateway) |
| Request header allow-list | include **`Authorization`** (so the agent can propagate the user's token to the Gateway) (**VERIFY** the setting name) |

Environment variables for `trc-agent`:

```dotenv
TRC_AGENT_GATEWAY_URL=https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
TRC_AGENT_GATEWAY_AUTH=propagate          # or client_credentials (then set TRC_AGENT_TOKEN_URL / CLIENT_ID / CLIENT_SECRET / SCOPE)
TRC_AGENT_REGION=<region>
TRC_AGENT_MODEL_ID=<inference profile id enabled in your account>
TRC_AGENT_WRITE_ACTIONS_ENABLED=false
TRC_AGENT_TURN_TIMEOUT_S=90
TRC_AGENT_GUARDRAIL_ID=                   # optional Bedrock Guardrail id
# Secrets: TRC_AGENT_TICKET_SECRET, TRC_AGENT_LOG_SALT from Secrets Manager.
```

### 3.8 Test the deployment

Get a user token from your IdP (any method your IdP supports, e.g. an auth-code/PKCE flow or a test app registration), then invoke the agent runtime. The exact URL is shown in the Runtime details; the shape is (**VERIFY**):

```bash
export TOKEN=<access token>
export SESSION=$(uuidgen | tr -d '-' | tr 'A-Z' 'a-z')$(date +%s)   # ≥ 33 chars is typical; VERIFY the min length

curl -s "https://bedrock-agentcore.$AWS_REGION.amazonaws.com/runtimes/<URL-encoded-runtime-ARN>/invocations?qualifier=DEFAULT" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $SESSION" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"'$SESSION'","user_id":"<your upn>","message":"Show me the TRC dashboard summary"}' | python -m json.tool
```

Check, in order, if something fails:

1. Agent Runtime logs (CloudWatch → `/aws/bedrock-agentcore/runtimes/...`): did the request validate? did it reach the Gateway?
2. Gateway: does the target list 29 tools? Is inbound JWT accepted?
3. MCP runtime logs: `UNAUTHENTICATED` means identity didn't arrive (Part 6).
4. Every log line carries the same `request_id`, which is also sent as `X-Correlation-Id` to on-prem.

### 3.9 Observability

The images start under `opentelemetry-instrument`, so traces/metrics flow to AgentCore Observability/CloudWatch (enable the Runtime's observability setting and CloudWatch Transaction Search if needed, **VERIFY**). Suggested alarms: `UPSTREAM_SCHEMA_MISMATCH` count (contract drift), `UPSTREAM_TIMEOUT`/`UNAVAILABLE` rate, circuit-breaker opens, tool latency p95, `NEEDS_CONFIRMATION` vs executed ratio. Logs contain only hashed member/provider references (`phi_ref`), not names or clinical text.

---

## Part 4 – Wire the real on-prem API

The code treats the on-prem API as an assumption isolated in three places. Do this **in a non-production environment first**.

1. **Routes** – `src/trc_mcp/clients/base.py` → `DEFAULT_ROUTES` maps each of 29 operations (`Op`) to `METHOD /path`. Override without code changes:

   ```dotenv
   TRC_MCP_ENDPOINT_OVERRIDES_JSON={"GET_MEMBER":"GET /api/v2/trc/members/{memberId}","SEND_NOTIFICATION":"POST /api/v2/trc/alerts"}
   ```

2. **Field mapping** – `src/trc_mcp/adapters/mappers.py` converts on-prem JSON to the contract models. The stub's fixture shape (`src/trc_mcp/clients/fixtures/members.json`) documents the assumed camelCase DTOs. Edit mappers to match real payloads. A mismatch yields `UPSTREAM_SCHEMA_MISMATCH`, not wrong data (by design).
3. **Auth/TLS** – `src/trc_mcp/clients/http.py` (OAuth2 client-credentials, `X-On-Behalf-Of`, `X-Correlation-Id`, `Idempotency-Key`). Set:

   ```dotenv
   TRC_MCP_BACKEND=http
   TRC_MCP_ONPREM_BASE_URL=https://<real host>
   TRC_MCP_TOKEN_URL=<token endpoint>
   TRC_MCP_CLIENT_ID=<from Secrets Manager>
   TRC_MCP_CLIENT_SECRET=<from Secrets Manager>
   TRC_MCP_SCOPE=<api scope>
   TRC_MCP_CA_BUNDLE=/etc/ssl/guidewell/ca.pem
   ```

4. **Prove it** – add a contract test per tool against a sandbox (copy `tests/mcp/test_http_client.py` as a pattern), then re-run `pytest`. Redeploy the MCP image, bump the tag, update the Runtime, and re-sync the Gateway target.
5. **Medication reconciliation / TCM eligibility** (in the baseline design doc but not the prototype): when the on-prem APIs exist, add an `Op`, a mapper, a contract model and a tool following any file in `src/trc_mcp/tools/`, then add the tool name to `src/trc_agent/policy.py`. A contract test fails if the two lists drift.

---

## Part 5 – Go-live checklist

- [ ] Option A vs B decided; Gateway → MCP → on-prem path tested with real credentials.
- [ ] Gateway forwards user identity to the MCP target (otherwise on-prem can't do per-user authorization). Test with two different users.
- [ ] Hardening H1: verify the JWT signature/issuer/audience in the MCP server rather than trusting the Gateway.
- [ ] Hardening H2: pass the signed confirmation ticket to MCP so it can refuse writes lacking human approval.
- [ ] Write governance approved (who may approve, audit retention). Keep both flags `false` until then; enable MCP first in a controlled environment, then the agent.
- [ ] `update_review_status` semantics confirmed (implemented as a confirmation-gated **soft close**; final MRAT closure stays human-only).
- [ ] Secrets in Secrets Manager only; `ticket_secret` is not the dev default; `REQUIRE_AUTH=true`.
- [ ] Load test the 13-call member-record fan-out against on-prem rate limits.
- [ ] Security review of logs (no PHI), WAF/rate limits at GWChat edge, Bedrock Guardrail configured if required.

## Part 6 – Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pytest` can't import `trc_*` | Run `pip install -e .` inside the venv |
| Agent: "No inbound Authorization header to propagate" | `Authorization` isn't in the Runtime header allow-list, or the caller sent no token. Locally set `TRC_AGENT_GATEWAY_AUTH=none` |
| Tools return `UNAUTHENTICATED` | MCP didn't receive user identity (Gateway not forwarding JWT/`x-gw-user-id`). Locally set `TRC_MCP_REQUIRE_AUTH=false` |
| `FORBIDDEN` on a read | Token lacks `trc.read` (or `trc.records.read` for attachments) |
| Write returns `FORBIDDEN`/disabled | Expected until `TRC_MCP_WRITE_TOOLS_ENABLED=true` **and** `TRC_AGENT_WRITE_ACTIONS_ENABLED=true` and the user has `trc.write` |
| Confirmation rejected | Ticket expired (10 min), or `session_id`/`user_id` differs from the proposing request, or it was tampered with |
| Agent sees 0 tools | Gateway target not synced, or tool names don't match: expect `trc___<tool>` |
| `UPSTREAM_SCHEMA_MISMATCH` | On-prem JSON doesn't match mappers: fix `adapters/mappers.py` (this is the fail-closed safety net) |
| `UPSTREAM_TIMEOUT` on dashboards | On-prem slow; budget is MCP 5 s/10 s per attempt, agent tool 20 s/30 s, turn 90 s: tune `TRC_MCP_READ_TIMEOUT_S` / `TRC_AGENT_TOOL_TIMEOUT_S` together |
| Bedrock `AccessDenied`/model not found | Model access not granted, wrong region, or wrong inference-profile id |
| Image fails to start on AgentCore | Not built for `linux/arm64`, or port/protocol mismatch (agent 8080 HTTP, MCP 8000 MCP) |
| MCP runtime can't reach on-prem | Subnet routes/SG egress/DNS/CA bundle (Part 3.2) |

---

## Reference

### Environment variables

**Agent (`TRC_AGENT_*`)**

| Variable | Default | Notes |
|---|---|---|
| `GATEWAY_URL` | placeholder | Gateway MCP URL (locally the MCP server URL) |
| `GATEWAY_AUTH` | `propagate` | `propagate` · `client_credentials` · `none` (local only) |
| `TOKEN_URL` `CLIENT_ID` `CLIENT_SECRET` `SCOPE` | – | for `client_credentials` |
| `MODEL_ID` / `REGION` | Claude Sonnet profile / `us-east-1` | **VERIFY** |
| `TEMPERATURE` | 0.0 | keep at 0 |
| `GUARDRAIL_ID` / `GUARDRAIL_VERSION` | – / `DRAFT` | optional |
| `TURN_TIMEOUT_S` `TOOL_TIMEOUT_S` `WRITE_TOOL_TIMEOUT_S` | 90 / 20 / 30 | nested budget |
| `TOOL_RETRIES` | 1 | reads only |
| `MAX_TOOL_CALLS_PER_TURN` `MAX_PARALLEL_CALLS` | 24 / 6 | |
| `WRITE_ACTIONS_ENABLED` | false | |
| `TICKET_SECRET` `TICKET_TTL_S` | dev-only / 600 | secret from Secrets Manager |
| `LOG_LEVEL` | INFO | |

**MCP server (`TRC_MCP_*`)**

| Variable | Default | Notes |
|---|---|---|
| `BACKEND` | `stub` | `stub` · `http` |
| `ONPREM_BASE_URL` `CA_BUNDLE` | placeholder / – | |
| `TOKEN_URL` `CLIENT_ID` `CLIENT_SECRET` `SCOPE` | – | on-prem OAuth (assumed) |
| `ENDPOINT_OVERRIDES_JSON` | `{}` | route overrides by `Op` name |
| `CONNECT_TIMEOUT_S` `READ_TIMEOUT_S` `WRITE_TIMEOUT_S` `MAX_RETRIES` | 3 / 5 / 10 / 2 | |
| `BREAKER_FAILURE_THRESHOLD` `BREAKER_RESET_S` | 5 / 30 | |
| `REQUIRE_AUTH` | true | false = local dev only |
| `TRUST_UPSTREAM_JWT` `USER_HEADER` | true / `x-gw-user-id` | identity source |
| `WRITE_TOOLS_ENABLED` | false | |
| `MAX_PAGE_SIZE` `MAX_BULK_RESEND` `MAX_VALIDATION_BATCH` | 50 / 25 / 200 | |
| `LOG_SALT` `LOG_LEVEL` | dev-salt / INFO | salt for hashed ids; read from the real process environment, not `.env` |

### Repository layout

```
src/trc_contracts/  shared Pydantic contracts (Envelope, errors, 29 payload models)
src/trc_mcp/        FastMCP server: tools/, clients/ (stub+http), adapters/mappers.py, security, config
src/trc_agent/      Strands agent: agent.py, hooks, confirmation tickets, ledger, blocks, grounding, workflow
tests/              mcp/ · agent/ · integration/ (real MCP over HTTP, demo_trace)
scripts/            build_fixtures.py, gen_tool_catalog.py
Dockerfile.agent · Dockerfile.mcp · .env.example · docs/
```

### Safety defaults (summary)

Writes are off in both services; every write needs a human-approved, signed, expiring ticket; final MRAT closure can't be requested by the agent; tool failures surface as "unavailable", never as inferred data; logs hold hashed ids only.
