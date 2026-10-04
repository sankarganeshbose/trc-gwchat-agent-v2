"""GWChat Integration Agent service.

Division of labour (the central design rule):
  LLM (Strands)      -> intent understanding, tool selection, parallel fan-out, ONE short narrative sentence block
  Deterministic code -> input validation, tool allow-list/budget, write confirmation, retries/timeouts, evidence ledger,
                        block assembly, data-gap reporting, grounding check, confirmed-action execution
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

from strands import Agent
from strands.models import BedrockModel
from strands.tools.executors import ConcurrentToolExecutor

from .config import AgentSettings
from .logging import get_logger, ref
from .models.schemas import (
    GWChatRequest, GWChatResponse, ResponseStatus,
)
from .orchestration.caller import ResilientCaller
from .orchestration.local_tools import make_local_tools
from .policy import WRITE_TOOLS
from .prompts.trc_system_prompt import SYSTEM_PROMPT, build_user_turn
from .services import blocks as B
from .services.confirmation import TicketError, TicketSigner
from .services.grounding import check_narrative
from .services.hooks import ToolPolicyHook
from .services.ledger import ToolLedger, record_from_envelope

log = get_logger("trc_agent")


def default_model_factory(s: AgentSettings):
    kw: dict[str, Any] = {}
    if s.guardrail_id:
        kw.update(guardrail_id=s.guardrail_id, guardrail_version=s.guardrail_version)
    return BedrockModel(model_id=s.model_id, region_name=s.region, temperature=s.temperature, max_tokens=s.max_tokens, **kw)


class TrcAgentService:
    def __init__(self, settings: AgentSettings, connector, *, model_factory: Callable[[AgentSettings], Any] = default_model_factory):
        self.s, self.connector, self.model_factory = settings, connector, model_factory
        self.signer = TicketSigner(settings.ticket_secret, settings.ticket_ttl_s)

    # ───────────────────────── public entrypoint ─────────────────────────
    async def handle(self, req: GWChatRequest, inbound_authorization: str | None = None) -> GWChatResponse:
        started = time.perf_counter()
        ledger = ToolLedger()
        try:
            async with self.connector.open(inbound_authorization, req.request_id) as gw:
                caller = ResilientCaller(gw.caller, self.s)
                if req.confirmation:
                    resp = await self._execute_confirmed(req, caller, ledger)
                else:
                    resp = await asyncio.wait_for(self._run_llm_turn(req, gw, caller, ledger), timeout=self.s.turn_timeout_s)
        except asyncio.TimeoutError:
            resp = self._error(req, ledger, "The request timed out before completion. No data was inferred; please retry.", "TURN_TIMEOUT")
        except PermissionError:
            resp = self._error(req, ledger, "You are not authorized to use this service.", "UNAUTHENTICATED")
        except Exception as exc:  # noqa: BLE001
            log.exception("turn_failed", request_id=req.request_id)
            resp = self._error(req, ledger, "The TRC service is temporarily unavailable. No data was inferred.", type(exc).__name__)
        log.info("turn_done", request_id=req.request_id, session=ref(req.session_id), user=ref(req.user_id), intent=resp.intent,
                 status=resp.status.value, tools=[t.tool for t in resp.tool_trace], gaps=len(resp.data_gaps), warnings=resp.warnings,
                 latency_ms=int((time.perf_counter() - started) * 1000))
        return resp

    # ───────────────────────── LLM-driven turn ─────────────────────────
    async def _run_llm_turn(self, req: GWChatRequest, gw, caller, ledger: ToolLedger) -> GWChatResponse:
        hook = ToolPolicyHook(ledger=ledger, settings=self.s, signer=self.signer, user_id=req.user_id, session_id=req.session_id)
        local = make_local_tools(caller, ledger, self.s.max_parallel_calls)
        agent = Agent(
            model=self.model_factory(self.s), system_prompt=SYSTEM_PROMPT, tools=[*gw.agent_tools, *local], hooks=[hook],
            tool_executor=ConcurrentToolExecutor(),  # tool_use blocks emitted in one model step run in parallel
            callback_handler=None,
            trace_attributes={"gwchat.request_id": req.request_id, "gwchat.user_ref": ref(req.user_id) or "", "gwchat.session_ref": ref(req.session_id) or ""},
        )  # NEW Agent per request: request-scoped state, no clinical facts retained between turns
        ctx_json = json.dumps(req.context.model_dump(exclude_none=True), separators=(",", ":"))
        result = await agent.invoke_async(build_user_turn(req.message or "", ctx_json))
        narrative = str(result).strip()
        return self._assemble(req, ledger, narrative)

    # ───────────────────────── confirmed write (no LLM) ─────────────────────────
    async def _execute_confirmed(self, req: GWChatRequest, caller, ledger: ToolLedger) -> GWChatResponse:
        c = req.confirmation
        assert c is not None
        try:
            t = self.signer.verify(c.ticket, user_id=req.user_id, session_id=req.session_id)
        except TicketError as exc:
            return self._error(req, ledger, str(exc), "TICKET_INVALID", status=ResponseStatus.ERROR)
        if t.tool not in WRITE_TOOLS or not self.s.write_actions_enabled:
            return self._error(req, ledger, "This action is not permitted.", "POLICY_WRITE_DENIED")
        if c.decision == "reject":
            return GWChatResponse(request_id=req.request_id, session_id=req.session_id, intent="ACTION_CANCELLED",
                                  status=ResponseStatus.OK, message="Okay — the action was cancelled. Nothing was changed.")
        env = await caller.call(t.tool, {**t.args, "idempotency_key": t.idempotency_key})  # same key on every replay of this ticket
        ledger.add(record_from_envelope(t.tool, t.args, env, origin="executor"))
        return self._assemble(req, ledger, narrative=_describe_action(t.tool, env), deterministic=True)

    # ───────────────────────── assembly ─────────────────────────
    def _assemble(self, req: GWChatRequest, ledger: ToolLedger, narrative: str, deterministic: bool = False) -> GWChatResponse:
        blocks = B.build_blocks(ledger)
        gaps = B.build_gaps(ledger)
        warnings: list[str] = []
        if not deterministic:
            problems = check_narrative(narrative, ledger, req.message or "")
            if problems:
                warnings += problems
                narrative = B.fallback_summary(blocks, gaps)
        if ledger.pending and not narrative:
            narrative = "This action needs your confirmation."
        return GWChatResponse(
            request_id=req.request_id, session_id=req.session_id, intent=B.derive_intent(ledger),
            status=B.derive_status(ledger, blocks, gaps), message=narrative or B.fallback_summary(blocks, gaps), blocks=blocks,
            data_gaps=gaps, pending_actions=ledger.pending, tool_trace=B.build_trace(ledger), warnings=warnings)

    def _error(self, req: GWChatRequest, ledger: ToolLedger, msg: str, code: str, status: ResponseStatus = ResponseStatus.ERROR) -> GWChatResponse:
        return GWChatResponse(request_id=req.request_id, session_id=req.session_id, intent="ERROR", status=status, message=msg,
                              blocks=B.build_blocks(ledger), data_gaps=B.build_gaps(ledger), tool_trace=B.build_trace(ledger), warnings=[code])


def _describe_action(tool: str, env: dict) -> str:
    """Deterministic result text for a confirmed action — straight from the tool envelope."""
    if not env.get("ok"):
        e = env.get("error") or {}
        return f"The action was NOT completed ({e.get('code', 'ERROR')}): {e.get('message', 'unavailable')}. Nothing was changed unless a later check shows otherwise."
    d = env["data"] or {}
    replay = " (this request had already been processed — no duplicate was created)" if d.get("idempotent_replay") else ""
    if tool == "send_provider_notification":
        return f"Alert resent for {d['member_id']} via {d['channel']} — status {d['status']} (notification {d['notification_id']}); Proxy Task updated: {d['proxy_task_updated']}{replay}."
    if tool == "resend_notifications_bulk":
        return f"Bulk resend {d['batch_id']}: {len(d['accepted'])} of {d['requested']} accepted, {len(d['skipped'])} skipped."
    if tool == "escalate_to_provider_manager":
        return f"Escalation {d['escalation_id']} created for {d['member_id']} → {d.get('escalated_to')}{replay}."
    if tool == "update_review_status":
        return f"{d['member_id']} moved {d['previous_status']} → {d['new_status']} (transition {d['transition_id']}); awaiting HEDIS-nurse final closure in MRAT{replay}."
    if tool == "log_intervention_activity":
        return f"Activity {d['activity_id']} logged for {d['member_id']}{replay}."
    if tool == "request_worklist_export":
        return f"Export {d['job_id']} is {d['status']} ({d.get('row_count')} rows). Download link expires {d.get('expires_at')}."
    return "Action completed."
