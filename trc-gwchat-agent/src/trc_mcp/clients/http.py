"""Production HTTP client for the on-prem TRC APIs (httpx, async).

Cross-cutting concerns live here and nowhere else: auth token acquisition, TLS, timeouts, bounded retries with jittered
backoff, a tiny circuit breaker, correlation/identity headers and status->error mapping.
"""
from __future__ import annotations

import asyncio
import random
import time
import urllib.parse
from typing import Any, Mapping, Protocol

import httpx

from trc_contracts.common import ErrorCode

from ..config import Settings
from ..errors import OnPremError, from_status
from ..logging import get_logger
from .base import DEFAULT_ROUTES, CallContext, Op

log = get_logger("trc_mcp.http")


class TokenProvider(Protocol):
    async def get_token(self) -> str: ...


class ClientCredentialsTokenProvider:
    """OAuth2 client-credentials (ASSUMPTION). Token cached until 60s before expiry."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self._s, self._http = settings, http
        self._token: str | None = None
        self._exp = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        async with self._lock:
            if self._token and time.monotonic() < self._exp - 60:
                return self._token
            if not (self._s.token_url and self._s.client_id and self._s.client_secret):
                raise OnPremError(ErrorCode.UNAUTHENTICATED, "On-prem client credentials are not configured.")
            r = await self._http.post(
                self._s.token_url,
                data={"grant_type": "client_credentials", "client_id": self._s.client_id,
                      "client_secret": self._s.client_secret, "scope": self._s.scope},
            )
            if r.status_code != 200:
                raise OnPremError(ErrorCode.UNAUTHENTICATED, "Could not obtain on-prem access token.", upstream_status=r.status_code)
            body = r.json()
            self._token = body["access_token"]
            self._exp = time.monotonic() + float(body.get("expires_in", 300))
            return self._token


class CircuitBreaker:
    def __init__(self, threshold: int, reset_s: float):
        self.threshold, self.reset_s = threshold, reset_s
        self.failures, self.opened_at = 0, 0.0

    def allow(self) -> bool:
        if self.failures < self.threshold:
            return True
        if time.monotonic() - self.opened_at >= self.reset_s:  # half-open: let one through
            return True
        return False

    def ok(self) -> None:
        self.failures = 0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


class HttpOnPremClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None,
                 token_provider: TokenProvider | None = None):
        self._s = settings
        verify: Any = settings.ca_bundle or True
        timeout = httpx.Timeout(settings.read_timeout_s, connect=settings.connect_timeout_s,
                                write=settings.write_timeout_s)
        self._http = httpx.AsyncClient(base_url=settings.onprem_base_url, timeout=timeout, verify=verify,
                                       transport=transport, limits=httpx.Limits(max_connections=50))
        self._auth_http = httpx.AsyncClient(timeout=timeout, verify=verify, transport=transport)
        self._tokens = token_provider or ClientCredentialsTokenProvider(settings, self._auth_http)
        self._breaker = CircuitBreaker(settings.breaker_failure_threshold, settings.breaker_reset_s)
        self._routes = dict(DEFAULT_ROUTES)
        for name, spec in settings.endpoint_overrides.items():  # e.g. "GET /api/v2/trc/members/{memberId}"
            method, _, path = spec.partition(" ")
            self._routes[Op(name)] = (method.upper(), path.strip())

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._auth_http.aclose()

    def _url(self, op: Op, path: Mapping[str, str] | None) -> tuple[str, str]:
        method, tmpl = self._routes[op]
        try:
            return method, tmpl.format(**{k: urllib.parse.quote(str(v), safe="") for k, v in (path or {}).items()})
        except KeyError as exc:
            raise OnPremError(ErrorCode.INTERNAL, f"Missing path parameter {exc} for {op}.") from exc

    async def call(self, op: Op, *, ctx: CallContext, path=None, query=None, body=None) -> Any:
        method, url = self._url(op, path)
        # Retry only when replay is safe: reads, or writes carrying an idempotency key.
        safe_to_retry = method == "GET" or ctx.idempotency_key is not None
        attempts = 1 + (self._s.max_retries if safe_to_retry else 0)
        last: OnPremError | None = None
        for attempt in range(attempts):
            if not self._breaker.allow():
                raise OnPremError(ErrorCode.UPSTREAM_UNAVAILABLE, "Upstream circuit open; failing fast.", retryable=True)
            try:
                token = await self._tokens.get_token()
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "X-Correlation-Id": ctx.request_id,
                    "X-On-Behalf-Of": ctx.principal.user_id,
                    "X-Source-System": "gwchat-integration-agent",
                }
                if ctx.idempotency_key:
                    headers["Idempotency-Key"] = ctx.idempotency_key
                params = {k: v for k, v in (query or {}).items() if v is not None}
                per_try = self._s.read_timeout_s if method == "GET" else self._s.write_timeout_s
                resp = await self._http.request(method, url, params=params or None,
                                                json=body if body is not None else None, headers=headers,
                                                timeout=httpx.Timeout(per_try, connect=self._s.connect_timeout_s))
                if resp.status_code >= 400:
                    code = None
                    try:
                        code = resp.json().get("code")
                    except Exception:  # noqa: BLE001
                        pass
                    raise from_status(resp.status_code, body_code=code)
                self._breaker.ok()
                return resp.json()
            except httpx.TimeoutException:
                last = OnPremError(ErrorCode.UPSTREAM_TIMEOUT, "Upstream timed out.", retryable=True)
            except httpx.TransportError:
                last = OnPremError(ErrorCode.UPSTREAM_UNAVAILABLE, "Could not reach upstream.", retryable=True)
            except ValueError as exc:  # JSON decode
                raise OnPremError(ErrorCode.UPSTREAM_SCHEMA_MISMATCH, "Upstream returned non-JSON.") from exc
            except OnPremError as exc:
                if not exc.retryable:
                    raise
                last = exc
            self._breaker.fail()
            log.warning("onprem_retry", op=op.value, attempt=attempt + 1, code=last.code.value, request_id=ctx.request_id)
            if attempt + 1 < attempts:
                await asyncio.sleep(self._s.retry_backoff_s * (2**attempt) * (0.5 + random.random()))
        assert last is not None
        raise last
