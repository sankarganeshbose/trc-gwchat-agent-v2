from __future__ import annotations

import httpx
import pytest
import respx

from trc_contracts.common import ErrorCode
from trc_mcp.clients.base import CallContext, Op
from trc_mcp.clients.http import HttpOnPremClient
from trc_mcp.config import Settings
from trc_mcp.errors import OnPremError
from trc_mcp.security import Principal

BASE = "https://trc-api.onprem.test"


class Tok:
    async def get_token(self) -> str:
        return "tok-123"


def make(**kw) -> HttpOnPremClient:
    s = Settings(backend="http", onprem_base_url=BASE, retry_backoff_s=0.001, require_auth=False, **kw)
    return HttpOnPremClient(s, token_provider=Tok())


def ctx(key=None) -> CallContext:
    return CallContext(principal=Principal("u1"), request_id="corr-1", tool="t", idempotency_key=key)


@respx.mock
async def test_get_sends_identity_headers_and_quotes_path():
    route = respx.get(f"{BASE}/api/trc/members/HCC-1").mock(return_value=httpx.Response(200, json={"ok": 1}))
    out = await make().call(Op.GET_MEMBER, ctx=ctx(), path={"memberId": "HCC-1"})
    h = route.calls[0].request.headers
    assert out == {"ok": 1} and h["authorization"] == "Bearer tok-123" and h["x-correlation-id"] == "corr-1" and h["x-on-behalf-of"] == "u1"


@respx.mock
async def test_path_param_cannot_escape_route():
    route = respx.get(url__regex=rf"{BASE}/api/trc/members/.*").mock(return_value=httpx.Response(200, json={}))
    await make().call(Op.GET_MEMBER, ctx=ctx(), path={"memberId": "../../admin"})
    assert route.calls[0].request.url.raw_path == b"/api/trc/members/..%2F..%2Fadmin"


@respx.mock
async def test_retries_503_then_succeeds_for_get():
    route = respx.get(f"{BASE}/api/trc/summary").mock(side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"a": 1})])
    assert await make().call(Op.GET_SUMMARY, ctx=ctx()) == {"a": 1}
    assert route.call_count == 3


@respx.mock
async def test_retries_exhausted_raises_unavailable():
    respx.get(f"{BASE}/api/trc/summary").mock(return_value=httpx.Response(503))
    with pytest.raises(OnPremError) as e:
        await make(max_retries=1).call(Op.GET_SUMMARY, ctx=ctx())
    assert e.value.code == ErrorCode.UPSTREAM_UNAVAILABLE and e.value.retryable


@respx.mock
async def test_post_without_idempotency_key_is_never_retried():
    route = respx.post(f"{BASE}/api/trc/notifications").mock(return_value=httpx.Response(503))
    with pytest.raises(OnPremError):
        await make().call(Op.SEND_NOTIFICATION, ctx=ctx(None), body={"memberId": "HCC-1"})
    assert route.call_count == 1


@respx.mock
async def test_post_with_idempotency_key_retries_and_sends_header():
    route = respx.post(f"{BASE}/api/trc/notifications").mock(side_effect=[httpx.Response(502), httpx.Response(200, json={"ok": 1})])
    await make().call(Op.SEND_NOTIFICATION, ctx=ctx("key-1"), body={"memberId": "HCC-1"})
    assert route.call_count == 2 and all(c.request.headers["idempotency-key"] == "key-1" for c in route.calls)


@respx.mock
@pytest.mark.parametrize("status,code", [(400, ErrorCode.INVALID_ARGUMENT), (401, ErrorCode.UNAUTHENTICATED), (403, ErrorCode.FORBIDDEN),
                                         (404, ErrorCode.NOT_FOUND), (409, ErrorCode.CONFLICT), (422, ErrorCode.PRECONDITION_FAILED)])
async def test_status_mapping_no_retry_on_4xx(status, code):
    route = respx.get(f"{BASE}/api/trc/summary").mock(return_value=httpx.Response(status, json={"code": "X", "detail": "patient Jane Doe"}))
    with pytest.raises(OnPremError) as e:
        await make().call(Op.GET_SUMMARY, ctx=ctx())
    assert e.value.code == code and route.call_count == 1 and "Jane" not in e.value.message


@respx.mock
async def test_timeout_maps_to_upstream_timeout():
    respx.get(f"{BASE}/api/trc/summary").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(OnPremError) as e:
        await make(max_retries=0).call(Op.GET_SUMMARY, ctx=ctx())
    assert e.value.code == ErrorCode.UPSTREAM_TIMEOUT


@respx.mock
async def test_non_json_body_fails_closed():
    respx.get(f"{BASE}/api/trc/summary").mock(return_value=httpx.Response(200, text="<html>proxy error</html>"))
    with pytest.raises(OnPremError) as e:
        await make().call(Op.GET_SUMMARY, ctx=ctx())
    assert e.value.code == ErrorCode.UPSTREAM_SCHEMA_MISMATCH


@respx.mock
async def test_circuit_breaker_opens_after_threshold():
    route = respx.get(f"{BASE}/api/trc/summary").mock(return_value=httpx.Response(500))
    c = make(max_retries=0, breaker_failure_threshold=2, breaker_reset_s=60)
    for _ in range(2):
        with pytest.raises(OnPremError):
            await c.call(Op.GET_SUMMARY, ctx=ctx())
    with pytest.raises(OnPremError) as e:
        await c.call(Op.GET_SUMMARY, ctx=ctx())
    assert "circuit open" in e.value.message and route.call_count == 2


@respx.mock
async def test_endpoint_override_swaps_route_without_code_change():
    route = respx.get(f"{BASE}/api/v2/trc/members/HCC-9/overview").mock(return_value=httpx.Response(200, json={"v": 2}))
    c = make(endpoint_overrides_json='{"GET_MEMBER": "GET /api/v2/trc/members/{memberId}/overview"}')
    assert await c.call(Op.GET_MEMBER, ctx=ctx(), path={"memberId": "HCC-9"}) == {"v": 2} and route.called
