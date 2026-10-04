from __future__ import annotations

import asyncio

import pytest

from trc_agent.orchestration.caller import ResilientCaller
from trc_agent.orchestration.workflow import Step, member_record_plan, run_plan, validate_then_board_plan
from trc_agent.services.ledger import ToolLedger
from tests.agent.helpers import agent_settings


class Recorder:
    """Fake ToolCaller recording concurrency and ordering."""

    def __init__(self, fail=(), delay=0.02):
        self.fail, self.delay, self.active, self.max_active, self.order = set(fail), delay, 0, 0, []

    async def call(self, tool, args):
        self.order.append(tool)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.delay)
        self.active -= 1
        if tool in self.fail:
            return {"ok": False, "data": None, "error": {"code": "UPSTREAM_UNAVAILABLE", "message": "x", "retryable": False}, "meta": {}}
        data = {"provider_id": "PRV-1000"} if tool == "get_provider_outreach" else {}
        return {"ok": True, "data": data, "error": None, "meta": {"source_system": "S"}}


async def test_member_record_fans_out_in_parallel_and_respects_dependency():
    rec, led = Recorder(), ToolLedger()
    res = await run_plan(member_record_plan("HCC-4471829"), rec, led, max_parallel=6)
    assert rec.max_active == 6, "independent reads must run concurrently (bounded by max_parallel)"
    assert rec.order.index("get_provider_contacts") > rec.order.index("get_provider_outreach"), "dependent step ran too early"
    assert len(res) == 13 and all(v["ok"] for v in res.values()) and len(led.records) == 13


async def test_dependent_step_skipped_not_fabricated_when_parent_fails():
    rec, led = Recorder(fail={"get_provider_outreach"}), ToolLedger()
    res = await run_plan(member_record_plan("HCC-4471829"), rec, led)
    assert "get_provider_contacts" not in rec.order
    assert res["contacts"]["error"]["code"] == "PRECONDITION_FAILED" and res["outreach"]["ok"] is False
    assert sum(1 for r in led.records if r.ok) == 11  # everything else still delivered (partial result)


async def test_validate_runs_before_board_and_summary_then_those_two_in_parallel():
    rec, led = Recorder(), ToolLedger()
    await run_plan(validate_then_board_plan(), rec, led)
    assert rec.order[0] == "validate_claims" and set(rec.order[1:]) == {"get_closure_board", "get_validation_summary"}
    assert rec.max_active == 2


async def test_cycle_fails_closed():
    steps = [Step("a", "t", after=("b",)), Step("b", "t", after=("a",))]
    with pytest.raises(ValueError):
        await run_plan(steps, Recorder(), ToolLedger())


class Flaky:
    def __init__(self, codes):
        self.codes, self.n = list(codes), 0

    async def call(self, tool, args):
        self.n += 1
        code = self.codes.pop(0) if self.codes else None
        if code:
            return {"ok": False, "data": None, "error": {"code": code, "message": "x", "retryable": True}, "meta": {}}
        return {"ok": True, "data": {}, "error": None, "meta": {}}


async def test_resilient_caller_retries_reads_but_not_unkeyed_writes():
    s = agent_settings(tool_retries=2)
    r = Flaky(["UPSTREAM_TIMEOUT", "RATE_LIMITED"])
    assert (await ResilientCaller(r, s).call("get_member_details", {}))["ok"] and r.n == 3
    w = Flaky(["UPSTREAM_TIMEOUT"])
    assert not (await ResilientCaller(w, s).call("send_provider_notification", {}))["ok"] and w.n == 1
    wk = Flaky(["UPSTREAM_TIMEOUT"])
    assert (await ResilientCaller(wk, s).call("send_provider_notification", {"idempotency_key": "tk-1"}))["ok"] and wk.n == 2


async def test_resilient_caller_stops_after_bounded_retries():
    s = agent_settings(tool_retries=2)
    r = Flaky(["UPSTREAM_TIMEOUT"] * 10)
    out = await ResilientCaller(r, s).call("get_trc_summary", {})
    assert out["ok"] is False and r.n == 3


async def test_member_record_end_to_end_against_stub(inproc):
    led = ToolLedger()
    res = await run_plan(member_record_plan("HCC-4471829"), inproc, led)
    assert all(v["ok"] for v in res.values()), {k: v["error"] for k, v in res.items() if not v["ok"]}
    assert res["contacts"]["data"]["provider_id"] == res["outreach"]["data"]["provider_id"] == "PRV-1000"
