"""Composite tools exposed to the LLM. They run deterministic plans (parallel fan-out through the Gateway) and return only a COMPACT,
fact-bounded headline to the model; full structured data goes to the ledger -> GWChat blocks. This keeps tokens low and the LLM
unable to restate (or alter) tables."""
from __future__ import annotations

from strands import tool

from ..policy import MEMBER_ID_RE
from ..services.ledger import ToolLedger
from .caller import ToolCaller
from .workflow import member_record_plan, run_plan, validate_then_board_plan


def make_local_tools(caller: ToolCaller, ledger: ToolLedger, max_parallel: int):
    @tool
    async def load_member_trc_record(member_id: str) -> dict:
        """Load the COMPLETE TRC record for one member in parallel (TRC status tracker, member/admission details, validation evidence,
        ADT timeline, discharge summary & medications, follow-up, risk, intervention, prior admissions, provider notification & contacts,
        medical-record list). Use for 'open/show/review the TRC record for <member>'.

        Args:
            member_id: Member HCCID, e.g. HCC-4471829.
        """
        if not MEMBER_ID_RE.match(member_id or ""):
            return {"status": "error", "message": "Invalid member id format."}
        res = await run_plan(member_record_plan(member_id), caller, ledger, max_parallel=max_parallel, intent="MEMBER_TRC_RECORD")
        sections = {k: ("ok" if v.get("ok") else f"UNAVAILABLE ({(v.get('error') or {}).get('code')})") for k, v in res.items()}
        head: dict = {"member_id": member_id, "sections": sections}
        if res["status"].get("ok"):
            d = res["status"]["data"]
            head.update(trc_status=d["trc_status"], eligibility=d["eligibility"], ineligibility_reason=d.get("ineligibility_reason"))
        if res["risk"].get("ok"):
            head["risk_tier"] = res["risk"]["data"]["tier"]
        if res["outreach"].get("ok"):
            o = res["outreach"]["data"]
            head.update(notification_status=o["status"], vista_upload=o["vista_upload"])
        if res["evidence"].get("ok"):
            e = res["evidence"]["data"]
            head.update(claim_status=e["claim_status"], rule_outcome=e["rule_outcome"])
        return head

    @tool
    async def run_validation_and_load_closure_board() -> dict:
        """Run the deterministic validation across all open TRC Proxy Tasks, THEN load the closure board and validation summary.
        Use for 'run the validation agent and show the closure board'. Validation does not soft-close anything.
        """
        res = await run_plan(validate_then_board_plan(), caller, ledger, max_parallel=max_parallel, intent="VALIDATION_RUN")
        out: dict = {"sections": {k: ("ok" if v.get("ok") else f"UNAVAILABLE ({(v.get('error') or {}).get('code')})") for k, v in res.items()}}
        if res["validate"].get("ok"):
            v = res["validate"]["data"]
            out.update(evaluated=v["evaluated"], passed=v["passed"], failed=v["failed"], persisted=v["persisted"])
        return out

    return [load_member_trc_record, run_validation_and_load_closure_board]
