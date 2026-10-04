from __future__ import annotations

import base64
import json

import pytest
from fastmcp import Client

from tests.conftest import call
from trc_contracts.common import ErrorCode
from trc_mcp.clients.base import Op
from trc_mcp.config import Settings
from trc_mcp.errors import OnPremError
from trc_mcp.security import Principal, principal_from_headers
from trc_mcp.server import build_server


def jwt(claims: dict) -> str:
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b({'alg': 'none'})}.{b(claims)}.sig"


def test_principal_from_jwt_scopes():
    s = Settings(require_auth=True)
    p = principal_from_headers({"Authorization": "Bearer " + jwt({"preferred_username": "nurse@gw", "scp": "trc.read trc.records.read"}), "x-correlation-id": "abc"}, s)
    assert p.user_id == "nurse@gw" and p.scopes == {"trc.read", "trc.records.read"} and p.correlation_id == "abc"


def test_missing_identity_rejected_when_auth_required():
    with pytest.raises(OnPremError) as e:
        principal_from_headers({}, Settings(require_auth=True))
    assert e.value.code == ErrorCode.UNAUTHENTICATED


async def test_missing_scope_is_forbidden(stub):
    s = Settings(require_auth=True, write_tools_enabled=True, log_level="ERROR")
    tc_server = build_server(s, client=stub)
    tc_server._trc_ctx.principal_resolver = lambda: Principal("u1", frozenset({"trc.read"}))  # no records scope, no write scope
    async with Client(tc_server) as c:
        a = await call(c, "get_attachments", member_id="HCC-4471829")
        w = await call(c, "send_provider_notification", member_id="HCC-2231087", reason="no write scope")
        ok = await call(c, "get_member_details", member_id="HCC-4471829")
    assert a["error"]["code"] == "FORBIDDEN" and w["error"]["code"] == "FORBIDDEN" and ok["ok"]
    assert [op for op, _ in stub.calls] == ["GET_MEMBER"]  # forbidden calls never reached on-prem


@pytest.mark.parametrize("code,retry", [(ErrorCode.UPSTREAM_TIMEOUT, True), (ErrorCode.UPSTREAM_UNAVAILABLE, True), (ErrorCode.FORBIDDEN, False)])
async def test_upstream_errors_map_to_structured_envelope(mcp_client, stub, code, retry):
    stub.fail_next[Op.GET_MEMBER] = OnPremError(code, "boom with PHI Dorothy Simmons", retryable=retry, upstream_status=503)
    r = await call(mcp_client, "get_member_details", member_id="HCC-4471829")
    assert r["ok"] is False and r["error"]["code"] == code.value and r["error"]["retryable"] is retry and r["data"] is None


async def test_malformed_upstream_fails_closed(mcp_client, stub):
    original = stub._h_get_risk
    stub._h_get_risk = lambda ctx, path, q, b: {"memberId": "HCC-4471829", "score": "high?"}  # missing tier/factors, wrong type
    r = await call(mcp_client, "get_risk_assessment", member_id="HCC-4471829")
    stub._h_get_risk = original
    assert r["ok"] is False and r["error"]["code"] == "UPSTREAM_SCHEMA_MISMATCH" and r["data"] is None
    assert "high?" not in json.dumps(r)  # offending payload never echoed


async def test_unexpected_exception_is_internal_without_leak(mcp_client, stub):
    stub._h_get_risk = lambda *a: (_ for _ in ()).throw(RuntimeError("secret connection string"))
    r = await call(mcp_client, "get_risk_assessment", member_id="HCC-4471829")
    assert r["error"]["code"] == "INTERNAL" and "secret" not in json.dumps(r)
