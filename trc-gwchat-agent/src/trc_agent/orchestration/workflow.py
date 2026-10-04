"""Declarative multi-tool plans + a tiny DAG executor.

A Step runs when all `after` steps finished. Independent steps in a layer run concurrently (bounded). A step whose inputs depend on a failed
parent is SKIPPED and reported as a data gap — never fabricated.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from ..services.ledger import ToolLedger, failure_envelope, record_from_envelope
from .caller import ToolCaller

Results = dict[str, dict]  # step id -> Envelope dict


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    args: Callable[[Results], dict[str, Any] | None] = field(default=lambda r: {})
    after: tuple[str, ...] = ()
    section: str | None = None  # label used by the MEMBER_RECORD block


async def run_plan(steps: list[Step], caller: ToolCaller, ledger: ToolLedger, *, max_parallel: int = 6,
                   origin: str = "plan", intent: str | None = None) -> Results:
    results: Results = {}
    pending = {s.id: s for s in steps}
    sem = asyncio.Semaphore(max_parallel)

    async def run(step: Step) -> None:
        args = step.args(results)
        if args is None:  # a dependency produced nothing usable
            results[step.id] = failure_envelope("PRECONDITION_FAILED", "Skipped: a prerequisite result was unavailable.")
            ledger.add(record_from_envelope(step.tool, {}, results[step.id], origin=origin, section=step.section, intent=intent))
            return
        async with sem:
            ledger.calls += 1
            env = await caller.call(step.tool, args)
        results[step.id] = env
        ledger.add(record_from_envelope(step.tool, args, env, origin=origin, section=step.section, intent=intent))

    while pending:
        ready = [s for s in pending.values() if all(d in results for d in s.after)]
        if not ready:  # cycle / missing dep: fail closed
            raise ValueError(f"Unresolvable plan dependencies: {sorted(pending)}")
        for s in ready:
            pending.pop(s.id)
        await asyncio.gather(*(run(s) for s in ready))
    return results


# ───────────────────────── plans ─────────────────────────
def member_record_plan(member_id: str) -> list[Step]:
    """Prototype p3 'Open the TRC record for X'. 11 independent reads (layer 1, parallel) + 1 dependent read (layer 2)."""
    m = {"member_id": member_id}
    return [
        Step("details", "get_member_details", lambda r: m, section="details"),
        Step("status", "get_member_trc_status", lambda r: m, section="trc_status"),
        Step("evidence", "get_validation_evidence", lambda r: m, section="validation_evidence"),
        Step("adt", "get_member_adt_timeline", lambda r: m, section="adt_timeline"),
        Step("discharge", "get_discharge_summary", lambda r: m, section="discharge_summary"),
        Step("meds", "get_discharge_medications", lambda r: m, section="discharge_medications"),
        Step("followup", "get_followup_status", lambda r: m, section="followup"),
        Step("risk", "get_risk_assessment", lambda r: m, section="risk"),
        Step("intervention", "get_intervention_status", lambda r: m, section="intervention"),
        Step("prior", "get_prior_admissions", lambda r: m, section="prior_admissions"),
        Step("outreach", "get_provider_outreach", lambda r: m, section="provider_notification"),
        Step("records", "get_attachments", lambda r: {"member_id": member_id}, section="medical_records"),
        # business dependency: provider id is only known after the outreach lookup
        Step("contacts", "get_provider_contacts",
             lambda r: ({"provider_id": r["outreach"]["data"]["provider_id"]}
                        if r["outreach"].get("ok") and r["outreach"]["data"].get("provider_id") else None),
             after=("outreach",), section="provider_contacts"),
    ]


def validate_then_board_plan() -> list[Step]:
    """Prototype p5. Sequential because the board/summary must reflect the validation run; board ∥ summary then run in parallel."""
    return [
        Step("validate", "validate_claims", lambda r: {}, section="validation_run"),
        Step("board", "get_closure_board", lambda r: {}, after=("validate",), section="closure_board"),
        Step("summary", "get_validation_summary", lambda r: {}, after=("validate",), section="validation_summary"),
    ]
