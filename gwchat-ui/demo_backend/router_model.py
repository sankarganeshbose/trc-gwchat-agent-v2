"""DemoRouterModel — a keyword router that stands in for Bedrock in the *demo backend only*.

It plays the role of the LLM: it reads the user's message, picks MCP tools (several at once => the agent runs them in parallel), and writes
a short narrative from tool results. EVERYTHING else is the real agent code (hooks, allow-list, confirmation tickets, ledger, blocks,
grounding) talking to the real FastMCP server. In production this class is replaced by BedrockModel (TRC_AGENT_MODEL_ID).
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterable

from strands.models import Model

LOCAL_TOOLS = {"load_member_trc_record", "run_validation_and_load_closure_board"}
MEMBER_RE = re.compile(r"\bHCC-\d{4,}\b", re.I)
WRITE_TOOLS = {"send_provider_notification", "resend_notifications_bulk", "escalate_to_provider_manager",
               "log_intervention_activity", "update_review_status", "request_worklist_export"}

CAPABILITIES = ("I can help with the Transition of Care (TRC) HEDIS workflow: the TRC dashboard and worklist, a member's TRC record, "
                "status, ADT timeline, risk, medications and follow-up, provider notifications, validation, records, the closure board, "
                "and (with your confirmation) resending alerts, escalating, soft-closing or exporting. Try asking about a member by their HCC member ID.")


# ───────────────────────────── message helpers ─────────────────────────────
def _text_of(content) -> str:
    return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and "text" in b)


def user_turn(messages) -> tuple[str, dict]:
    """(user message, request context) from the first user message built by the agent's `build_user_turn`."""
    raw = next((_text_of(m["content"]) for m in messages if m["role"] == "user" and "<user_message>" in _text_of(m["content"])), "")
    msg = re.search(r"<user_message>(.*?)</user_message>", raw, re.S)
    ctx = re.search(r"<request_context>(.*?)</request_context>", raw, re.S)
    try:
        c = json.loads(ctx.group(1)) if ctx else {}
    except json.JSONDecodeError:
        c = {}
    return (msg.group(1).strip() if msg else raw), c


def tool_rounds(messages) -> list[list[tuple[str, dict, dict]]]:
    """One entry per model tool round (= one user message carrying toolResults): [(tool, input, parsed_result_json)]."""
    uses: dict[str, tuple[str, dict]] = {}
    rounds: list[list[tuple[str, dict, dict]]] = []
    for m in messages:
        this: list[tuple[str, dict, dict]] = []
        for b in m["content"]:
            if "toolUse" in b:
                uses[b["toolUse"]["toolUseId"]] = (b["toolUse"]["name"], b["toolUse"].get("input", {}))
            if "toolResult" in b:
                tr = b["toolResult"]
                name, args = uses.get(tr["toolUseId"], ("?", {}))
                parsed: dict = {}
                for c in tr.get("content", []):
                    if "json" in c:
                        parsed = c["json"]
                    elif "text" in c:
                        try:
                            parsed = json.loads(c["text"])
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"_text": c["text"]}
                this.append((name, args, parsed))
        if this:
            rounds.append(this)
    return rounds


# ───────────────────────────── routing (phase 1) ─────────────────────────────
def route(text: str, ctx: dict) -> tuple[str, object]:
    """('tools', [(name, args), ...]) or ('text', narrative). Deterministic keyword rules; unknown => no tools (never guesses)."""
    t = text.lower()
    ids = MEMBER_RE.findall(text)
    mid = ids[0].upper() if ids else ctx.get("selected_member_id")
    has = lambda *w: any(re.search(w_, t) for w_ in w)  # noqa: E731

    # Guardrail demo: final MRAT closure is human-only; no tool exists for it.
    if has(r"\b(close|finali[sz]e)\b.*\bmrat\b", r"\bmrat\b.*\b(close|finali[sz]e)\b") and not has(r"status|show|view|awaiting|pending|queue"):
        return "text", ("Final MRAT closure is performed by the HEDIS nurse in MRAT. I can't do that, but I can show this member's MRAT review status "
                        "or soft-close a member whose validation has passed (with your confirmation).")

    # ── writes (the agent's hook will intercept these and ask for confirmation) ──
    if has(r"\bbulk\b", r"resend.*(non-?responsive|all|failed|pending)") and not ids:
        return "tools", [("list_provider_outreach", {})]
    if has(r"\bresend\b") and mid:
        return "tools", [("send_provider_notification", {"member_id": mid, "reason": "Resend TRC provider alert requested from GWChat"})]
    if has(r"\bescalat") and mid:
        return "tools", [("escalate_to_provider_manager", {"member_id": mid, "reason": "Provider non-responsive after TRC alert; escalated from GWChat"})]
    if has(r"soft.?clos") and mid:
        return "tools", [("update_review_status", {"member_id": mid, "target_status": "SOFT_CLOSED", "reason": "Validation passed; routed to MRAT review"})]
    if has(r"\blog\b.*(intervention|activity)", r"(intervention|activity).*\blog\b") and mid:
        act = text.split(":", 1)[1].strip() if ":" in text else "Care coordinator outreach logged from GWChat"
        return "tools", [("log_intervention_activity", {"member_id": mid, "activity": act[:500]})]
    if has(r"\bexport\b"):
        args: dict = {"format": "PDF" if has(r"\bpdf\b") else "CSV"}
        if has(r"no upload|not uploaded|without upload"):
            args["provider_upload_status"] = "NOT_UPLOADED"
        return "tools", [("request_worklist_export", args)]

    # ── cohort / dashboard ──
    if has(r"run (the )?validation", r"validation agent", r"re-?run validate", r"\bvalidate\b"):
        return "tools", [("run_validation_and_load_closure_board", {})]
    if has(r"validation summary", r"validation (kpi|metrics)"):
        return "tools", [("get_validation_summary", {})]
    if has(r"closure board", r"\bkanban\b", r"\bboard\b"):
        return "tools", [("get_closure_board", {})]
    if has(r"not acknowledged", r"unacknowledged", r"non-?responsive"):
        return "tools", [("list_provider_outreach", {"unacknowledged_only": True})]
    if has(r"notification tracking", r"all (provider )?notifications") and not mid:
        return "tools", [("list_provider_outreach", {})]
    if has(r"breakdown", r"by facilit", r"by disposition", r"trend") and not mid:
        dim = "FACILITY" if has("facilit") else "DISPOSITION" if has("disposition") else "TREND" if has("trend") else "COMPONENT"
        return "tools", [("get_trc_metric_breakdown", {"dimension": dim})]
    if has(r"dashboard", r"how are we doing", r"overview", r"snapshot") and not has("facilit", "disposition", "trend", "component") and not mid:
        # Dashboard playbook: independent reads fan out in parallel (summary, four breakdowns, top no-upload members).
        return "tools", [("get_trc_summary", {})] + [("get_trc_metric_breakdown", {"dimension": d}) for d in ("COMPONENT", "FACILITY", "DISPOSITION", "TREND")] \
            + [("get_trc_worklist", {"sort_by": "risk_score_desc", "past_day3_no_upload_only": True, "risk_tier": "HIGH", "limit": 3})]
    if has(r"dashboard", r"\bkpi", r"how are we doing", r"overview", r"snapshot") or (has(r"\bsummary\b") and not mid):
        dim = "FACILITY" if has("facilit") else "DISPOSITION" if has("disposition") else "TREND" if has("trend") else "COMPONENT"
        return "tools", [("get_trc_summary", {}), ("get_trc_metric_breakdown", {"dimension": dim})]
    if has(r"worklist", r"no upload", r"not uploaded", r"day.?3", r"discharged in the last", r"\bmembers\b.*(risk|upload)") and not mid:
        a: dict = {"sort_by": "risk_score_desc"} if has("risk") else {}
        n = re.search(r"last (\d{1,3}) days", t)
        if n:
            a["lookback_days"] = int(n.group(1))
        if has(r"upload"):
            a["past_day3_no_upload_only"] = True
        if has(r"high.?risk"):
            a["risk_tier"] = "HIGH"
        return "tools", [("get_trc_worklist", a)]

    # ── member-scoped ──
    member_intents = [
        (r"\brecord\b|open the|full|everything|review", "load_member_trc_record", lambda m: {"member_id": m}),
        (r"\badt\b|timeline|events", "get_member_adt_timeline", lambda m: {"member_id": m}),
        (r"\brisk\b|readmission", "get_risk_assessment", lambda m: {"member_id": m}),
        (r"medication|meds", "get_discharge_medications", lambda m: {"member_id": m}),
        (r"follow.?up|pcp", "get_followup_status", lambda m: {"member_id": m}),
        (r"intervention", "get_intervention_status", lambda m: {"member_id": m}),
        (r"prior admission|history|previous admission", "get_prior_admissions", lambda m: {"member_id": m}),
        (r"audit", "get_member_audit_trail", lambda m: {"member_id": m}),
        (r"mrat", "get_mrat_review_status", lambda m: {"member_id": m}),
        (r"evidence|validation", "get_validation_evidence", lambda m: {"member_id": m}),
        (r"notif|outreach|alert|provider", "get_provider_outreach", lambda m: {"member_id": m}),
        (r"attachment|document|medical record|records", "get_attachments", lambda m: {"member_id": m}),
        (r"discharge", "get_discharge_summary", lambda m: {"member_id": m}),
        (r"detail|demograph|admission", "get_member_details", lambda m: {"member_id": m}),
        (r"status|where|stand|progress", "get_member_trc_status", lambda m: {"member_id": m}),
    ]
    for pat, tool, mk in member_intents:
        if has(pat):
            if not mid:
                return "text", ("Which member? Please give the member ID (format HCC-#######) or select a member card. "
                                "I don't look members up by name.")
            return "tools", [(tool, mk(mid))]
    if has(r"weather", r"joke", r"poem", r"stock", r"recipe", r"diagnos", r"treat"):
        return "text", "That's outside what I can help with. I only handle the TRC HEDIS workflow and don't give clinical advice."
    if mid:
        return "tools", [("get_member_trc_status", {"member_id": mid})]
    return "text", CAPABILITIES


# ───────────────────────────── narration (phase 2) ─────────────────────────────
def _data(parsed: dict) -> dict | None:
    return parsed.get("data") if parsed.get("ok", True) and isinstance(parsed.get("data"), dict) else None


def narrate(rounds: list[list[tuple[str, dict, dict]]]) -> str:
    """Short, number-bounded narrative using only values present in tool results. No identifiers, no completion claims."""
    calls = [c for r in rounds for c in r]
    if any(n in WRITE_TOOLS for n, _, _ in calls):
        return "This action needs your approval. Review the details below and Approve or Reject; nothing is changed until you approve."
    parts: list[str] = []
    failed = [n for n, _, p in calls if p.get("ok") is False]
    for name, _, parsed in calls:
        # local composite tools return a compact headline directly; MCP tools return the Envelope {ok, data, error, meta}
        d = parsed if name in LOCAL_TOOLS and "sections" in parsed else _data(parsed)
        if d is None:
            continue
        if name == "get_trc_summary":
            parts.append(f"{d['discharges_identified']:,} discharges identified; closure rate {d['closure_rate_pct']}%"
                         + (f" against a {d['plan_target_pct']}% plan target" if d.get("plan_target_pct") else "")
                         + f"; {d['no_upload_by_day3']} members have no provider upload by day 3 ({d['no_upload_by_day3_high_risk']} high-risk).")
        elif name == "get_trc_metric_breakdown":
            if not any(n == "get_trc_summary" for n, _, _ in calls) and not any(x.startswith("Showing the TRC") for x in parts):
                parts.append(f"Showing the TRC breakdown for {d['measurement_period']}.")
        elif name == "get_trc_worklist":
            if not any(n == "get_trc_summary" for n, _, _ in calls):
                parts.append(f"{d['total_matching']} matching members; showing {d['returned']}.")
        elif name == "list_provider_outreach":
            allowed = sum(1 for i in d["items"] if i.get("resend_allowed"))
            parts.append(f"{d['total_matching']} notifications match; {allowed} can be resent.")
        elif name == "get_member_trc_status":
            parts.append(f"Current TRC step: {d['trc_status'].replace('_', ' ').title()}; eligibility {d['eligibility'].title()}.")
        elif name == "get_risk_assessment":
            parts.append(f"Readmission risk is {d['tier']} (score {d['score']}); used for prioritization only.")
        elif name == "get_closure_board":
            parts.append("Closure board: " + ", ".join(f"{c['label']} {c['count']}" for c in d["columns"]) + ".")
        elif name == "run_validation_and_load_closure_board":
            parts.append(f"Validation run complete: {d.get('evaluated', 0)} evaluated, {d.get('passed', 0)} passed, {d.get('failed', 0)} failed; closure board and summary loaded.")
        elif name == "get_validation_summary":
            parts.append(f"{d['evaluated_last_90_days']} tasks evaluated in 90 days; {d['claims_validated_pct']}% claims validated.")
        elif name == "load_member_trc_record":
            sec = d.get("sections", {})
            ok = sum(1 for v in sec.values() if v == "ok")
            parts.append(f"Loaded {ok} of {len(sec)} record sections; TRC step {str(d.get('trc_status', 'unknown')).replace('_', ' ').title()}.")
        else:
            parts.append(f"Retrieved {name.replace('get_', '').replace('_', ' ')}.")
    if failed:
        parts.append("Some data is unavailable right now; see the data gaps below. I have not inferred it.")
    return " ".join(parts) or "No data could be retrieved."


def plan_second_round(text: str, ctx: dict, rounds) -> list[tuple[str, dict]] | None:
    """Bulk resend: after listing outreach, propose ONE write with the explicit ids the tool says are resendable."""
    calls = [c for r in rounds for c in r]
    if len(rounds) == 1 and calls and calls[0][0] == "list_provider_outreach" and re.search(r"\bbulk\b|resend", text.lower()) and not MEMBER_RE.search(text):
        d = _data(calls[0][2])
        ids = [i["member_id"] for i in (d or {}).get("items", []) if i.get("resend_allowed")]
        if ids:
            return [("resend_notifications_bulk", {"member_ids": ids[:25], "reason": "Bulk resend to non-responsive providers from GWChat"})]
    return None


class DemoRouterModel(Model):
    def __init__(self) -> None:
        self.config: dict = {}
        self._n = 0

    def update_config(self, **model_config):
        self.config.update(model_config)

    def get_config(self):
        return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kw):  # pragma: no cover
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncIterable[dict]:
        text, ctx = user_turn(messages)
        rounds = tool_rounds(messages)
        if not rounds:
            kind, payload = route(text, ctx)
        else:
            nxt = plan_second_round(text, ctx, rounds)
            kind, payload = ("tools", nxt) if nxt else ("text", narrate(rounds))
        self._n += 1
        yield {"messageStart": {"role": "assistant"}}
        if kind == "tools":
            for i, (name, args) in enumerate(payload):  # type: ignore[misc]
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"demo{self._n}_{i}", "name": name}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}}
                yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": payload}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}
