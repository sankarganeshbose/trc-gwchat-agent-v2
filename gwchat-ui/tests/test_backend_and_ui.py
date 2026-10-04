"""Starts the real demo backend (real agent + real FastMCP server + stub on-prem) as a subprocess and drives it, then drives the Streamlit app headlessly."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def backend():
    p1, p2 = _port(), _port()
    env = {**os.environ, "PYTHONPATH": str(ROOT), "DEMO_PORT": str(p1), "DEMO_MCP_PORT": str(p2), "DEMO_ONPREM_LATENCY_MS": "5"}
    proc = subprocess.Popen([sys.executable, "-m", "demo_backend.server"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{p1}"
    for _ in range(150):
        try:
            if httpx.get(url + "/ping", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("demo backend did not start")
    yield url
    proc.kill()


def call(url, **kw):
    return httpx.post(url + "/invocations", json={"session_id": "sess-12345678", "user_id": "tester", **kw}, timeout=60).json()


def test_member_record_fans_out_through_mcp(backend):
    r = call(backend, message="Open the TRC record for HCC-4471829")
    assert r["status"] == "OK" and r["blocks"][0]["type"] == "MEMBER_RECORD"
    assert len(r["tool_trace"]) == 13 and len(r["_demo"]["onprem_calls"]) == 13


def test_write_needs_confirmation_then_executes_once(backend):
    httpx.post(backend + "/demo/reset")
    r = call(backend, message="Soft-close HCC-3345510")
    assert r["status"] == "NEEDS_CONFIRMATION" and not r["blocks"] and r["_demo"]["onprem_calls"] == []   # nothing reached on-prem
    t = r["pending_actions"][0]["ticket"]
    a = call(backend, confirmation={"ticket": t, "decision": "approve"})
    assert a["status"] == "OK" and a["blocks"][0]["type"] == "ACTION_RESULT"
    b = call(backend, confirmation={"ticket": t, "decision": "approve"})
    assert "already been processed" in b["message"]


def test_guardrails(backend):
    assert call(backend, message="Open the TRC record for Dorothy Simmons")["status"] == "NARRATIVE_ONLY"
    assert call(backend, message="Close HCC-3345510 in MRAT")["tool_trace"] == []
    g = call(backend, message="Show the TRC status for HCC-0000000")
    assert g["status"] == "UNAVAILABLE" and g["data_gaps"]


def test_bridge_message_confirm_and_config(backend):
    from gwchat_ui.bridge_core import Bridge
    httpx.post(backend + "/demo/reset")
    b = Bridge(url=backend + "/invocations")
    p = b.handle({"kind": "message", "nonce": "1", "message": "Resend the failed provider alert for HCC-2231087"})
    assert p["ok"] and p["nonce"] == "1" and p["reply"]["status"] == "NEEDS_CONFIRMATION" and "_demo" not in p["reply"] and p["steps"]
    a = b.handle({"kind": "confirm", "nonce": "2", "ticket": p["reply"]["pending_actions"][0]["ticket"], "decision": "approve"})
    assert a["reply"]["blocks"][0]["type"] == "ACTION_RESULT"
    assert b.handle({"kind": "ping", "nonce": "3"})["ok"]
    bad = Bridge(url="http://127.0.0.1:9/invocations").handle({"kind": "message", "nonce": "4", "message": "hi"})
    assert bad["ok"] is False and "Could not reach" in bad["error"]
    b.handle({"kind": "configure", "nonce": "5", "token": "secret"})
    assert b.token == "secret" and "secret" not in str(b.handle({"kind": "ping", "nonce": "6"}))


def test_dashboard_playbook_fans_out_in_parallel_reads(backend):
    r = call(backend, message="How are we doing on TRC? Show the dashboard.")
    assert [b["type"] for b in r["blocks"]].count("METRIC_BREAKDOWN") == 4 and r["blocks"][0]["type"] == "KPI_SUMMARY"
    assert {t["tool"] for t in r["tool_trace"]} == {"get_trc_summary", "get_trc_metric_breakdown", "get_trc_worklist"}


def test_devserver_serves_page_and_api(backend):
    from starlette.testclient import TestClient
    from gwchat_ui.bridge_core import Bridge
    from gwchat_ui.devserver import make_app
    c = TestClient(make_app(Bridge(url=backend + "/invocations")))
    assert "GuideWell" in c.get("/index.html").text and c.get("/app.js").status_code == 200 and c.get("/chart.umd.js").status_code == 200
    assert c.post("/api/chat", json={"kind": "message", "nonce": "x", "message": "Show the validation summary"}).json()["reply"]["blocks"][0]["type"] == "VALIDATION_SUMMARY"
