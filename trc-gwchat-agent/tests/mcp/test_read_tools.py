from __future__ import annotations

from tests.conftest import call


async def test_member_details(mcp_client):
    r = await call(mcp_client, "get_member_details", member_id="HCC-4471829")
    assert r["ok"] and r["error"] is None
    d = r["data"]
    assert d["name"] == "Dorothy Simmons" and d["trc_status"] == "PROVIDER_NOTIFIED"
    assert d["diagnosis_code"] == "I50.9" and d["followup_due"] == "2026-08-03"
    assert r["meta"]["read_only"] is True and r["meta"]["tool"] == "get_member_details"


async def test_unknown_member_is_not_found_not_exception(mcp_client):
    r = await call(mcp_client, "get_member_details", member_id="HCC-0000000")
    assert r["ok"] is False and r["error"]["code"] == "NOT_FOUND" and r["data"] is None


async def test_invalid_member_id_rejected_at_mcp_boundary(mcp_client):
    r = await call(mcp_client, "get_member_details", member_id="x; DROP TABLE")
    assert r.get("mcp_error") is True


async def test_p1_prompt_filters_past_day3_no_upload_ranked_by_risk(mcp_client):
    r = await call(mcp_client, "get_trc_worklist", lookback_days=30, past_day3_no_upload_only=True)
    items = r["data"]["items"]
    assert items and all(i["past_day3_no_upload"] and i["provider_upload_status"] == "NOT_UPLOADED" for i in items)
    scores = [i["risk_score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    assert r["data"]["applied_filters"]["past_day3_no_upload_only"] is True


async def test_worklist_filters_and_paging(mcp_client):
    r = await call(mcp_client, "get_trc_worklist", risk_tier="HIGH", limit=1)
    assert r["data"]["returned"] == 1 and r["data"]["total_matching"] >= 2 and r["data"]["next_cursor"] == "1"
    r2 = await call(mcp_client, "get_trc_worklist", risk_tier="HIGH", limit=1, cursor=r["data"]["next_cursor"])
    assert r2["data"]["items"][0]["member_id"] != r["data"]["items"][0]["member_id"]


async def test_excluded_member_status_has_reason_and_no_steps(mcp_client):
    r = await call(mcp_client, "get_member_trc_status", member_id="HCC-2298871")
    assert r["data"]["eligibility"] == "INELIGIBLE" and "EXPIRED" in r["data"]["ineligibility_reason"] and r["data"]["steps"] == []


async def test_status_tracker_marks_failed_notification(mcp_client):
    r = await call(mcp_client, "get_member_trc_status", member_id="HCC-2231087")
    states = {s["key"]: s["state"] for s in r["data"]["steps"]}
    assert states["PROVIDER_NOTIFIED"] == "FAILED" and states["DISCHARGE_IDENTIFIED"] == "DONE"


async def test_adt_raw_hl7_only_on_request(mcp_client):
    a = await call(mcp_client, "get_member_adt_timeline", member_id="HCC-4471829")
    b = await call(mcp_client, "get_member_adt_timeline", member_id="HCC-4471829", include_raw_hl7=True)
    assert all(e["raw_hl7"] is None for e in a["data"]["events"])
    assert b["data"]["events"][-1]["event_type"] == "A03" and b["data"]["events"][-1]["raw_hl7"].startswith("MSH|")


async def test_followup_overdue_flag(mcp_client):
    r = await call(mcp_client, "get_followup_status", member_id="HCC-4471829")  # due 08-03, stub 'today' 08-05
    assert r["data"]["overdue"] is True and r["data"]["days_until_due"] == -2


async def test_outreach_unacknowledged_and_resend_allowed(mcp_client):
    r = await call(mcp_client, "list_provider_outreach", unacknowledged_only=True)
    assert r["data"]["items"] and all(i["status"] != "ACKNOWLEDGED" for i in r["data"]["items"])
    for i in r["data"]["items"]:
        assert i["resend_allowed"] == (i["status"] in ("FAILED", "PENDING"))


async def test_provider_contacts_masked(mcp_client):
    r = await call(mcp_client, "get_provider_contacts", provider_id="PRV-1000")
    assert all(c["value"] is None or "*" in c["value"] for c in r["data"]["contacts"])


async def test_summary_and_breakdowns(mcp_client):
    s = await call(mcp_client, "get_trc_summary")
    assert s["data"]["discharges_identified"] == 1284 and s["data"]["no_upload_by_day3_high_risk"] == 23
    m = await call(mcp_client, "get_trc_metric_breakdown", dimension="TREND")
    assert len(m["data"]["points"]) == 12 and m["data"]["points"][-1]["value"] == 58.0


async def test_attachments_and_link_are_read_only_metadata(mcp_client):
    a = await call(mcp_client, "get_attachments", member_id="HCC-4471829")
    assert a["data"]["items"] and all(i["read_only"] for i in a["data"]["items"])
    l = await call(mcp_client, "get_attachment_access_link", attachment_id=a["data"]["items"][0]["attachment_id"])
    assert l["data"]["url"].startswith("https://") and l["data"]["audit_logged"] is True
    audit = await call(mcp_client, "get_member_audit_trail", member_id="HCC-4471829")
    assert any(e["action"] == "RECORD_ACCESSED" for e in audit["data"]["events"])


async def test_validate_claims_outcomes_deterministic(mcp_client):
    r = await call(mcp_client, "validate_claims", member_ids=["HCC-9903341", "HCC-4471829"])
    out = {x["member_id"]: x for x in r["data"]["results"]}
    assert out["HCC-9903341"]["outcome"] == "PASSED"
    assert out["HCC-4471829"]["outcome"] == "FAILED" and "No Provider Vista / Link upload" in out["HCC-4471829"]["reasons"]
    assert r["data"]["evaluated"] == 2 and r["meta"]["read_only"] is False and r["meta"]["idempotency_key"].startswith("auto-")


async def test_closure_board_columns(mcp_client):
    r = await call(mcp_client, "get_closure_board")
    assert [c["status"] for c in r["data"]["columns"]] == ["DISCHARGE_IDENTIFIED", "PROVIDER_NOTIFIED", "VALIDATION_PASSED", "SOFT_CLOSED"]
    assert sum(c["count"] for c in r["data"]["columns"]) == 9  # 10 members minus the EXCLUDED one
