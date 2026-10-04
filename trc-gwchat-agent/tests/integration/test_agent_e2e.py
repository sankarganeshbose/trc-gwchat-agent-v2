"""Strands agent -> (MCP over HTTP) -> FastMCP -> stub on-prem. The only fakes are the LLM and the network edge (Gateway/on-prem)."""
from __future__ import annotations


import pytest

from trc_agent.agent import TrcAgentService
from trc_agent.models.schemas import BlockType, GWChatRequest, ResponseStatus
from trc_agent.orchestration.gateway import StrandsGatewayConnector
from tests.agent.helpers import agent_settings
from tests.integration.conftest import ScriptedModel

pytestmark = pytest.mark.asyncio(loop_scope="function")


def svc(url, script, **kw):
    s = agent_settings(gateway_url=url, **kw)
    return TrcAgentService(s, StrandsGatewayConnector(s), model_factory=lambda _s: ScriptedModel(script)), s


def req(msg=None, **kw):
    return GWChatRequest(session_id="sess-e2e-0001", user_id="sankar", message=msg, **kw)


async def test_p1_prompt_parallel_read_tools_to_structured_blocks(live_mcp):
    url, stub = live_mcp
    stub.calls.clear()
    service, _ = svc(url, [
        {"tools": [("get_trc_summary", {}), ("get_trc_worklist", {"lookback_days": 30, "past_day3_no_upload_only": True, "sort_by": "risk_score_desc"})]},
        {"text": "Two HIGH-risk members are past day 3 with no Provider Vista upload, including HCC-4471829."},
    ])
    r = await service.handle(req("Show members discharged recently where the provider has not uploaded documents by day 3, ranked by risk."))
    assert r.status == ResponseStatus.OK and r.warnings == [] and r.data_gaps == []
    assert {b.type for b in r.blocks} == {BlockType.KPI_SUMMARY, BlockType.WORKLIST}
    wl = next(b for b in r.blocks if b.type == BlockType.WORKLIST)
    assert wl.data["items"][0]["member_id"] == "HCC-4471829" and wl.data["applied_filters"]["past_day3_no_upload_only"] is True
    assert r.intent == "TRC_DASHBOARD+TRC_WORKLIST" and {t.tool for t in r.tool_trace} == {"get_trc_summary", "get_trc_worklist"}
    assert [op for op, _ in stub.calls] == ["GET_SUMMARY", "GET_WORKLIST"] or {op for op, _ in stub.calls} == {"GET_SUMMARY", "GET_WORKLIST"}


async def test_hallucinated_identifier_is_replaced_by_deterministic_summary(live_mcp):
    url, _ = live_mcp
    service, _ = svc(url, [{"tools": [("get_trc_worklist", {"limit": 3})]}, {"text": "HCC-9999999 is the most urgent member."}])
    r = await service.handle(req("list the worklist"))
    assert "UNGROUNDED_IDENTIFIER:HCC-9999999" in r.warnings and "HCC-9999999" not in r.message and "TRC worklist" in r.message
    assert r.blocks[0].type == BlockType.WORKLIST  # the data itself is untouched


async def test_member_record_composite_tool_returns_full_record_block(live_mcp):
    url, stub = live_mcp
    service, _ = svc(url, [{"tools": [("load_member_trc_record", {"member_id": "HCC-4471829"})]}, {"text": "Record loaded for HCC-4471829; provider alert is PENDING."}])
    r = await service.handle(req("Open the TRC record for Dorothy Simmons (HCC-4471829)"))
    rec = next(b for b in r.blocks if b.type == BlockType.MEMBER_RECORD)
    assert r.status == ResponseStatus.OK and set(rec.data) >= {"details", "trc_status", "validation_evidence", "adt_timeline", "discharge_summary",
                                                               "discharge_medications", "followup", "risk", "intervention", "prior_admissions",
                                                               "provider_notification", "medical_records", "provider_contacts"}
    assert r.intent == "MEMBER_TRC_RECORD" and rec.data["details"]["name"] == "Dorothy Simmons"


async def test_out_of_scope_gets_narrative_only_and_no_tools(live_mcp):
    url, stub = live_mcp
    stub.calls.clear()
    service, _ = svc(url, [{"text": "I can only help with the TRC measure workflow."}])
    r = await service.handle(req("Check my Monday calendar"))
    assert r.status == ResponseStatus.NARRATIVE_ONLY and r.blocks == [] and stub.calls == []


async def test_upstream_failure_is_retried_once_then_reported_as_gap_not_inferred(live_mcp):
    url, stub = live_mcp
    original = stub._h_get_summary
    stub._h_get_summary = lambda *a: (_ for _ in ()).throw(__import__("trc_mcp.errors", fromlist=["OnPremError"]).OnPremError(
        __import__("trc_contracts.common", fromlist=["ErrorCode"]).ErrorCode.UPSTREAM_UNAVAILABLE, "down", retryable=True, upstream_status=503))
    stub.calls.clear()
    try:
        service, _ = svc(url, [{"tools": [("get_trc_summary", {})]}, {"text": "The TRC summary is currently unavailable."}])
        r = await service.handle(req("How are we doing on TRC?"))
    finally:
        stub._h_get_summary = original
    assert r.status == ResponseStatus.UNAVAILABLE and r.blocks == [] and r.data_gaps[0].code == "UPSTREAM_UNAVAILABLE" and r.data_gaps[0].retryable
    assert [op for op, _ in stub.calls].count("GET_SUMMARY") == 2  # original + exactly one agent-level retry


async def test_write_requires_confirmation_then_executes_exactly_once(live_mcp):
    url, stub = live_mcp
    service, _ = svc(url, [
        {"tools": [("send_provider_notification", {"member_id": "HCC-2231087", "reason": "resend failed fax", "idempotency_key": "llm-made-up"})]},
        {"text": "The resend for HCC-2231087 is awaiting your confirmation."},
    ])
    r1 = await service.handle(req("Resend the failed alert for Marcus Webb"))
    assert r1.status == ResponseStatus.NEEDS_CONFIRMATION and len(r1.pending_actions) == 1 and not r1.warnings
    assert not any(op == "SEND_NOTIFICATION" for op, _ in stub.calls), "write executed before user confirmation!"
    assert next(m for m in stub.members if m["memberId"] == "HCC-2231087")["notification"]["status"] == "FAILED"
    ticket = r1.pending_actions[0].ticket

    approve = GWChatRequest(session_id="sess-e2e-0001", user_id="sankar", confirmation={"ticket": ticket, "decision": "approve"})
    r2 = await service.handle(approve)
    assert r2.status == ResponseStatus.OK and r2.blocks[0].type == BlockType.ACTION_RESULT and "Alert resent for HCC-2231087" in r2.message
    assert next(m for m in stub.members if m["memberId"] == "HCC-2231087")["notification"]["status"] == "SENT"

    r3 = await service.handle(approve)  # double-click / network retry of the SAME approval
    assert r3.blocks[0].data["idempotent_replay"] is True and "no duplicate" in r3.message
    sends = [op for op, tool in stub.calls if op == "SEND_NOTIFICATION"]
    assert len(sends) == 2  # both reached the server, the SERVER deduplicated via the ticket-derived key
    audit = [e for e in stub.audit["HCC-2231087"] if e["action"] == "ALERT_RESENT"]
    assert len(audit) == 1


async def test_confirmation_rejected_tampered_wrong_user_and_disabled(live_mcp):
    url, stub = live_mcp
    service, s = svc(url, [{"tools": [("update_review_status", {"member_id": "HCC-3345510", "target_status": "SOFT_CLOSED", "reason": "validated"})]}, {"text": "Awaiting confirmation."}])
    r1 = await service.handle(req("soft close HCC-3345510"))
    t = r1.pending_actions[0].ticket
    mk = lambda **kw: GWChatRequest(session_id=kw.pop("session_id", "sess-e2e-0001"), user_id=kw.pop("user_id", "sankar"), confirmation={"ticket": kw.pop("ticket", t), "decision": kw.pop("decision", "approve")})
    assert (await service.handle(mk(decision="reject"))).message.startswith("Okay — the action was cancelled")
    assert (await service.handle(mk(ticket=t[:-3] + "AAA"))).status == ResponseStatus.ERROR
    assert (await service.handle(mk(user_id="someone-else"))).status == ResponseStatus.ERROR
    assert (await service.handle(mk(session_id="sess-other-9999"))).status == ResponseStatus.ERROR
    assert next(m for m in stub.members if m["memberId"] == "HCC-3345510")["trc"]["status"] == "VALIDATION_PASSED"  # nothing changed
    off, _ = svc(url, [{"text": "x"}], write_actions_enabled=False)
    assert (await off.handle(mk())).warnings == ["POLICY_WRITE_DENIED"]


async def test_p5_validation_then_board_via_composite_tool(live_mcp):
    url, stub = live_mcp
    stub.calls.clear()
    service, _ = svc(url, [{"tools": [("run_validation_and_load_closure_board", {})]}, {"text": "Validation ran across open tasks; board updated."}])
    r = await service.handle(req("Run the validation agent and show me the TRC closure board."))
    assert {b.type for b in r.blocks} == {BlockType.VALIDATION_RUN, BlockType.CLOSURE_BOARD, BlockType.VALIDATION_SUMMARY}
    ops = [op for op, _ in stub.calls]
    assert ops[0] == "RUN_CLAIM_VALIDATION" and set(ops[1:]) == {"GET_CLOSURE_BOARD", "GET_VALIDATION_SUMMARY"}
