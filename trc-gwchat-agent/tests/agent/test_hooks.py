from __future__ import annotations

from types import SimpleNamespace

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent

from trc_agent.services.hooks import ToolPolicyHook
from trc_agent.services.ledger import ToolLedger
from tests.agent.helpers import agent_settings, signer


def mk(**kw):
    s = agent_settings(**kw)
    ledger = ToolLedger()
    return ToolPolicyHook(ledger=ledger, settings=s, signer=signer(s), user_id="u1", session_id="sess-0001"), ledger


def before(hook, name, inp, use_id="t1"):
    ev = BeforeToolCallEvent(agent=SimpleNamespace(), selected_tool=None, tool_use={"toolUseId": use_id, "name": name, "input": inp}, invocation_state={})
    hook.before(ev)
    return ev


def after(hook, name, inp, result, use_id="t1", cancel=None):
    ev = AfterToolCallEvent(agent=SimpleNamespace(), selected_tool=None, tool_use={"toolUseId": use_id, "name": name, "input": inp},
                            invocation_state={}, result=result, cancel_message=cancel)
    hook.after(ev)
    return ev


ENV_OK = {"ok": True, "data": {"member_id": "HCC-4471829"}, "error": None, "meta": {"tool": "x", "source_system": "S"}}
ENV_RETRY = {"ok": False, "data": None, "error": {"code": "UPSTREAM_TIMEOUT", "message": "t", "retryable": True}, "meta": {}}


def test_unknown_tool_blocked_even_with_gateway_prefix():
    h, led = mk()
    ev = before(h, "trc-mcp___drop_database", {})
    assert ev.cancel_tool and "POLICY_UNKNOWN_TOOL" in ev.cancel_tool and led.blocked == [("drop_database", "POLICY_UNKNOWN_TOOL")]


def test_gateway_prefix_is_stripped_for_allowed_tool():
    h, led = mk()
    assert before(h, "trc-mcp___get_member_details", {"member_id": "HCC-4471829"}).cancel_tool is False and led.calls == 1


def test_bad_member_id_blocked():
    h, _ = mk()
    assert "POLICY_BAD_ID" in before(h, "get_member_details", {"member_id": "1; DROP"}).cancel_tool
    assert "POLICY_BAD_ID" in before(h, "resend_notifications_bulk", {"member_ids": ["HCC-1234567", "bad id"]}).cancel_tool


def test_write_tool_is_never_executed_it_is_queued_with_ticket():
    h, led = mk()
    ev = before(h, "send_provider_notification", {"member_id": "HCC-2231087", "reason": "resend", "idempotency_key": "llm-chosen-key"})
    assert "QUEUED_FOR_USER_CONFIRMATION" in ev.cancel_tool and led.calls == 0
    p = led.pending[0]
    assert p.tool == "send_provider_notification" and "idempotency_key" not in p.arguments  # LLM cannot choose the key
    v = signer().verify(p.ticket, user_id="u1", session_id="sess-0001")
    assert v.args == p.arguments


def test_writes_disabled_flag_blocks_without_ticket():
    h, led = mk(write_actions_enabled=False)
    assert "POLICY_WRITES_DISABLED" in before(h, "update_review_status", {"member_id": "HCC-3345510"}).cancel_tool and not led.pending


def test_call_budget_enforced():
    h, _ = mk(max_tool_calls_per_turn=2)
    for i in range(2):
        assert before(h, "get_trc_summary", {}, f"t{i}").cancel_tool is False
    assert "POLICY_BUDGET" in before(h, "get_trc_summary", {}, "t9").cancel_tool


def test_after_records_evidence_and_skips_cancelled_calls():
    h, led = mk()
    after(h, "get_member_details", {"member_id": "HCC-4471829"}, {"status": "success", "structuredContent": ENV_OK, "content": []})
    after(h, "send_provider_notification", {}, {"status": "error", "content": []}, use_id="t2", cancel="queued")
    assert len(led.records) == 1 and led.records[0].ok and led.records[0].tool == "get_member_details"


def test_retryable_read_failure_retried_once_then_recorded():
    h, led = mk()
    inp = {"member_id": "HCC-4471829"}
    r = {"status": "error", "structuredContent": ENV_RETRY, "content": []}
    e1 = after(h, "get_member_details", inp, r)
    assert e1.retry is True and not led.records
    e2 = after(h, "get_member_details", inp, r)
    assert e2.retry is False and len(led.records) == 1 and not led.records[0].ok


def test_malformed_tool_result_fails_closed():
    h, led = mk()
    after(h, "get_member_details", {"member_id": "HCC-4471829"}, {"status": "success", "content": [{"text": "Dorothy is fine"}]})
    assert led.records[0].ok is False and led.records[0].error["code"] == "UPSTREAM_SCHEMA_MISMATCH"
