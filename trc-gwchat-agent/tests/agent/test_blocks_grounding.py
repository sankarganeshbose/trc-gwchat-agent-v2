from __future__ import annotations

from trc_agent.models.schemas import BlockType, ResponseStatus
from trc_agent.orchestration.workflow import member_record_plan, run_plan
from trc_agent.services import blocks as B
from trc_agent.services.grounding import check_narrative
from trc_agent.services.ledger import ToolLedger, record_from_envelope


def env(data, tool="t"):
    return {"ok": True, "data": data, "error": None, "meta": {"source_system": "S", "as_of": "2026-08-05T09:00:00Z"}}


def test_blocks_are_verbatim_tool_data():
    led = ToolLedger()
    data = {"items": [{"member_id": "HCC-4471829"}], "returned": 1}
    led.add(record_from_envelope("get_trc_worklist", {"lookback_days": 14}, env(data), origin="llm"))
    blocks = B.build_blocks(led)
    assert blocks[0].type == BlockType.WORKLIST and blocks[0].data == data and blocks[0].source_systems == ["S"]


def test_duplicate_identical_calls_collapse():
    led = ToolLedger()
    for _ in range(2):
        led.add(record_from_envelope("get_trc_summary", {}, env({"x": 1}), origin="llm"))
    assert len(B.build_blocks(led)) == 1


def test_status_matrix():
    led = ToolLedger()
    assert B.derive_status(led, [], []) == ResponseStatus.NARRATIVE_ONLY
    led.add(record_from_envelope("get_trc_summary", {}, env({"x": 1}), origin="llm"))
    b, g = B.build_blocks(led), B.build_gaps(led)
    assert B.derive_status(led, b, g) == ResponseStatus.OK
    led.add(record_from_envelope("get_trc_worklist", {}, {"ok": False, "data": None, "error": {"code": "UPSTREAM_TIMEOUT", "message": "t", "retryable": True}, "meta": {}}, origin="llm"))
    g = B.build_gaps(led)
    assert B.derive_status(led, b, g) == ResponseStatus.PARTIAL and g[0].code == "UPSTREAM_TIMEOUT" and g[0].retryable
    only_fail = ToolLedger()
    only_fail.add(record_from_envelope("get_trc_worklist", {}, {"ok": False, "data": None, "error": {"code": "X", "message": "m"}, "meta": {}}, origin="llm"))
    assert B.derive_status(only_fail, [], B.build_gaps(only_fail)) == ResponseStatus.UNAVAILABLE


async def test_member_record_block_composed_with_gap_for_failed_section(inproc, stub):
    from trc_mcp.clients.base import Op
    from trc_mcp.errors import OnPremError
    from trc_contracts.common import ErrorCode
    stub.fail_next[Op.GET_RISK] = OnPremError(ErrorCode.UPSTREAM_UNAVAILABLE, "down", retryable=False)
    led = ToolLedger()
    await run_plan(member_record_plan("HCC-4471829"), inproc, led)
    blocks, gaps = B.build_blocks(led), B.build_gaps(led)
    rec = blocks[0]
    assert rec.type == BlockType.MEMBER_RECORD and rec.title == "TRC record — HCC-4471829"
    assert "risk" not in rec.data and "provider_notification" in rec.data and "details" in rec.data
    assert [g.section for g in gaps] == ["risk"] and B.derive_status(led, blocks, gaps) == ResponseStatus.PARTIAL


def test_grounding_rejects_invented_identifiers_and_completion_claims():
    led = ToolLedger()
    led.add(record_from_envelope("get_trc_worklist", {}, env({"items": [{"member_id": "HCC-4471829"}]}), origin="llm"))
    assert check_narrative("HCC-4471829 needs outreach.", led, "show worklist") == []
    assert check_narrative("HCC-9999999 needs outreach.", led, "show worklist") == ["UNGROUNDED_IDENTIFIER:HCC-9999999"]
    assert "UNSUPPORTED_COMPLETION_CLAIM" in check_narrative("The alert has been sent to the provider.", led, "resend")
    assert check_narrative("The resend is awaiting your confirmation.", led, "resend") == []
    assert check_narrative("The user-supplied HCC-5551234 id is unknown.", led, "look up HCC-5551234") == []


def test_fallback_summary_lists_gaps():
    led = ToolLedger()
    led.add(record_from_envelope("get_risk_assessment", {}, {"ok": False, "data": None, "error": {"code": "NOT_FOUND", "message": "m"}, "meta": {}}, origin="llm", section="risk"))
    assert "risk (NOT_FOUND)" in B.fallback_summary([], B.build_gaps(led))
