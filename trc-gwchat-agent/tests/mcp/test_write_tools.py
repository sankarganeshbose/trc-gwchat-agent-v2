from __future__ import annotations

from fastmcp import Client

from tests.conftest import call
from trc_mcp.config import Settings
from trc_mcp.server import build_server


async def test_writes_disabled_by_flag(stub):
    s = Settings(require_auth=False, write_tools_enabled=False, log_level="ERROR")
    async with Client(build_server(s, client=stub)) as c:
        r = await call(c, "send_provider_notification", member_id="HCC-2231087", reason="resend failed fax")
    assert r["ok"] is False and r["error"]["code"] == "FORBIDDEN"
    assert not any(op == "SEND_NOTIFICATION" for op, _ in stub.calls)


async def test_resend_failed_alert_updates_state(mcp_client):
    r = await call(mcp_client, "send_provider_notification", member_id="HCC-2231087", reason="resend failed fax", idempotency_key="key-12345678")
    assert r["ok"] and r["data"]["status"] == "SENT" and r["data"]["proxy_task_updated"] is True and r["meta"]["read_only"] is False
    again = await call(mcp_client, "get_provider_outreach", member_id="HCC-2231087")
    assert again["data"]["status"] == "SENT"


async def test_resend_rejected_for_acknowledged(mcp_client):
    r = await call(mcp_client, "send_provider_notification", member_id="HCC-9903341", reason="should not be allowed")
    assert r["ok"] is False and r["error"]["code"] == "PRECONDITION_FAILED"


async def test_idempotent_replay_does_not_resend(mcp_client, stub):
    a = await call(mcp_client, "send_provider_notification", member_id="HCC-4471829", reason="pending alert", idempotency_key="idem-aaaaaaaa")
    b = await call(mcp_client, "send_provider_notification", member_id="HCC-4471829", reason="pending alert", idempotency_key="idem-aaaaaaaa")
    assert a["ok"] and b["ok"] and b["data"]["idempotent_replay"] is True
    audit = await call(mcp_client, "get_member_audit_trail", member_id="HCC-4471829")
    assert [e["action"] for e in audit["data"]["events"]].count("ALERT_RESENT") == 1


async def test_idempotency_key_reuse_with_different_payload_conflicts(mcp_client):
    await call(mcp_client, "send_provider_notification", member_id="HCC-4471829", reason="first", idempotency_key="idem-bbbbbbbb")
    r = await call(mcp_client, "send_provider_notification", member_id="HCC-4471829", reason="different", idempotency_key="idem-bbbbbbbb")
    assert r["ok"] is False and r["error"]["code"] == "CONFLICT"


async def test_bulk_resend_reports_skips_not_failures(mcp_client):
    r = await call(mcp_client, "resend_notifications_bulk", member_ids=["HCC-2231087", "HCC-9903341"], reason="non-responsive providers")
    assert r["ok"] and [a["member_id"] for a in r["data"]["accepted"]] == ["HCC-2231087"]
    assert r["data"]["skipped"][0]["member_id"] == "HCC-9903341" and r["data"]["requested"] == 2


async def test_bulk_resend_cap_enforced_server_side(stub):
    s = Settings(require_auth=False, write_tools_enabled=True, max_bulk_resend=2, log_level="ERROR")
    async with Client(build_server(s, client=stub)) as c:
        r = await call(c, "resend_notifications_bulk", member_ids=["HCC-0000001", "HCC-0000002", "HCC-0000003"], reason="too many at once")
    assert r["ok"] is False and r["error"]["code"] == "INVALID_ARGUMENT"
    assert not any(op == "BULK_RESEND_NOTIFICATIONS" for op, _ in stub.calls)


async def test_soft_close_only_from_validation_passed(mcp_client):
    ok = await call(mcp_client, "update_review_status", member_id="HCC-3345510", target_status="SOFT_CLOSED", reason="validation passed")
    assert ok["ok"] and ok["data"]["previous_status"] == "VALIDATION_PASSED" and ok["data"]["new_status"] == "SOFT_CLOSED"
    bad = await call(mcp_client, "update_review_status", member_id="HCC-2231087", target_status="SOFT_CLOSED", reason="not validated")
    assert bad["ok"] is False and bad["error"]["code"] == "PRECONDITION_FAILED"


async def test_cannot_request_final_mrat_closure(mcp_client):
    r = await call(mcp_client, "update_review_status", member_id="HCC-3345510", target_status="MRAT_CLOSED", reason="try to bypass the nurse")
    assert r.get("mcp_error") is True


async def test_export_returns_link_not_bytes(mcp_client):
    r = await call(mcp_client, "request_worklist_export", format="CSV", risk_tier="HIGH")
    assert r["ok"] and r["data"]["download_url"].startswith("https://") and r["data"]["row_count"] >= 1
