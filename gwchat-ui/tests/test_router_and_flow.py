import re

from demo_backend.router_model import route
from gwchat_ui.client import AgentReply
from gwchat_ui.flow import build_dot, build_steps


def test_member_status_routes_to_one_tool():
    assert route("Show the TRC status for member HCC-4471829", {}) == ("tools", [("get_member_trc_status", {"member_id": "HCC-4471829"})])


def test_selected_member_context_resolves_this_member():
    kind, calls = route("show the risk", {"selected_member_id": "HCC-2231087"})
    assert kind == "tools" and calls == [("get_risk_assessment", {"member_id": "HCC-2231087"})]


def test_name_only_is_never_resolved():
    kind, text = route("Open the TRC record for Dorothy Simmons", {})
    assert kind == "text" and "member ID" in text


def test_writes_route_to_write_tools_and_mrat_close_is_refused():
    assert route("Resend the failed provider alert for HCC-2231087", {})[1][0][0] == "send_provider_notification"
    kind, text = route("Close HCC-3345510 in MRAT", {})
    assert kind == "text" and "HEDIS nurse" in text


def test_canned_text_never_contains_member_ids():
    for p in ["hello", "Open the record for Jane Doe", "Tell me a joke"]:
        kind, text = route(p, {})
        assert kind == "text" and not re.search(r"HCC-\d", text)


def _reply(trace, blocks=0):
    return AgentReply(True, data={"intent": "X", "status": "OK", "tool_trace": trace, "blocks": [{}] * blocks, "data_gaps": [],
                                  "_demo": {"onprem_calls": [{"tool": "get_member_details", "method": "GET", "route": "/api/trc/members/HCC-1", "ms": 5, "status": "ok"}]}},
                      http_ms=120)


def test_flow_graph_and_steps_cover_ok_queued_and_blocked():
    r = _reply([{"tool": "get_member_details", "ok": True, "outcome": "ok", "latency_ms": 60},
                {"tool": "send_provider_notification", "ok": True, "outcome": "queued_for_confirmation"},
                {"tool": "get_x", "ok": False, "outcome": "blocked", "error_code": "TOOL_NOT_ALLOWED"}], blocks=1)
    dot = build_dot(r)
    assert "AgentCore Gateway" in dot and "WRITE queued" in dot and "blocked" in dot and "GET /api/trc/members/HCC-1" in dot
    steps = build_steps(r)
    assert steps[0]["Hop"].startswith("GWChat UI") and steps[-1]["Hop"].startswith("Agent → GWChat")
    assert any("WRITE" in s["What happened"] for s in steps)


def test_out_of_scope_wins_over_selected_member_context():
    kind, payload = route("Tell me a joke", {"selected_member_id": "HCC-4471829"})
    assert kind == "text" and "outside" in payload
