from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import call

MEMBER_TOOLS = ["get_member_details", "get_member_trc_status", "get_member_adt_timeline", "get_risk_assessment", "get_intervention_status",
                "get_prior_admissions", "get_member_audit_trail", "get_discharge_summary", "get_discharge_medications",
                "get_followup_status", "get_provider_outreach", "get_validation_evidence", "get_mrat_review_status"]
FIX = json.loads((Path(__file__).parents[2] / "src/trc_mcp/clients/fixtures/members.json").read_text())


@pytest.mark.parametrize("member", [m["memberId"] for m in FIX])
async def test_every_member_tool_succeeds_for_every_prototype_member(mcp_client, member):
    """Contract-vs-fixture sweep: guards mapper/contract drift against all 10 prototype members (incl. EXCLUDED/MRAT_CLOSED)."""
    for tool in MEMBER_TOOLS:
        r = await call(mcp_client, tool, member_id=member)
        assert r["ok"], (tool, member, r.get("error"))
