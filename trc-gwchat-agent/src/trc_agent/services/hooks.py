"""Strands hooks = the deterministic guardrail layer around LLM-driven tool use."""
from __future__ import annotations

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from ..config import AgentSettings
from ..logging import get_logger, ref
from ..policy import ALLOWED_MCP_TOOLS, LOCAL_TOOLS, MEMBER_ID_RE, WRITE_TOOLS, canonical
from .confirmation import TicketSigner
from .ledger import ToolLedger, parse_tool_result, record_from_envelope

log = get_logger("trc_agent.hooks")
RETRYABLE_CODES = {"UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE", "RATE_LIMITED"}


class ToolPolicyHook(HookProvider):
    def __init__(self, *, ledger: ToolLedger, settings: AgentSettings, signer: TicketSigner, user_id: str, session_id: str):
        self.ledger, self.s, self.signer, self.user_id, self.session_id = ledger, settings, signer, user_id, session_id
        self._attempts: dict[str, int] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    # ───────────── before ─────────────
    def before(self, event: BeforeToolCallEvent) -> None:
        name = canonical(event.tool_use["name"])
        args = event.tool_use.get("input") or {}
        if name not in ALLOWED_MCP_TOOLS and name not in LOCAL_TOOLS:
            return self._block(event, name, "POLICY_UNKNOWN_TOOL", "This tool is not permitted for the TRC agent.")
        if self.ledger.calls >= self.s.max_tool_calls_per_turn:
            return self._block(event, name, "POLICY_BUDGET", "Tool-call budget for this request is exhausted.")
        for key in ("member_id",):
            if key in args and not (isinstance(args[key], str) and MEMBER_ID_RE.match(args[key])):
                return self._block(event, name, "POLICY_BAD_ID", "member_id has an invalid format. Ask the user for a valid member id.")
        for mid in args.get("member_ids") or []:
            if not (isinstance(mid, str) and MEMBER_ID_RE.match(mid)):
                return self._block(event, name, "POLICY_BAD_ID", "member_ids contains an invalid id.")
        if name in WRITE_TOOLS:
            if not self.s.write_actions_enabled:
                return self._block(event, name, "POLICY_WRITES_DISABLED", "Write actions are not enabled in this environment.")
            args = {k: v for k, v in args.items() if k != "idempotency_key"}  # the key is derived from the ticket, never from the LLM
            pending = self.signer.issue(user_id=self.user_id, session_id=self.session_id, tool=name, args=args)
            self.ledger.pending.append(pending)
            event.cancel_tool = ("QUEUED_FOR_USER_CONFIRMATION: This action has NOT been executed. The user must approve it in GWChat. "
                                 "Tell the user it is awaiting their confirmation and describe it in one sentence. Do not retry.")
            log.info("write_queued", tool=name, user=ref(self.user_id))
            return
        self.ledger.calls += 1

    def _block(self, event: BeforeToolCallEvent, name: str, code: str, msg: str) -> None:
        self.ledger.blocked.append((name, code))
        event.cancel_tool = f"{code}: {msg}"
        log.warning("tool_blocked", tool=name, code=code)

    # ───────────── after ─────────────
    def after(self, event: AfterToolCallEvent) -> None:
        name = canonical(event.tool_use["name"])
        if event.cancel_message or name in LOCAL_TOOLS:
            return  # blocked/queued calls are not evidence; local composite tools record their own sub-calls
        result = event.result if isinstance(event.result, dict) else {"status": "error"}
        env = parse_tool_result(result)
        err = env.get("error") or {}
        use_id = event.tool_use["toolUseId"]
        if (not env["ok"] and err.get("code") in RETRYABLE_CODES and name not in WRITE_TOOLS
                and self._attempts.get(use_id, 0) < 1 and self.ledger.calls < self.s.max_tool_calls_per_turn):
            self._attempts[use_id] = self._attempts.get(use_id, 0) + 1
            self.ledger.calls += 1
            event.retry = True  # Strands discards this result and re-invokes the tool (reads/compute only; writes never auto-retry)
            return
        self.ledger.add(record_from_envelope(name, event.tool_use.get("input") or {}, env, origin="llm"))
