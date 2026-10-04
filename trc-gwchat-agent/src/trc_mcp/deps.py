"""Tool dependency container + the single execution wrapper every tool goes through."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, TypeVar

from pydantic import BaseModel, ValidationError

from trc_contracts.common import Envelope, ErrorCode, Meta, ToolFailure

from .clients.base import CallContext, Op, OnPremClient
from .config import Settings
from .errors import OnPremError
from .logging import get_logger, phi_ref
from .security import READ, Principal

M = TypeVar("M", bound=BaseModel)
log = get_logger("trc_mcp.tools")


@dataclass
class ToolContext:
    client: OnPremClient
    settings: Settings
    principal_resolver: Callable[[], Principal]


def derive_idempotency_key(principal: Principal, tool: str, payload: Mapping[str, Any]) -> str:
    """Fallback when the caller supplies no key: stable within a 10-minute bucket so accidental duplicates collapse."""
    bucket = int(time.time() // 600)
    raw = json.dumps({"u": principal.user_id, "t": tool, "p": payload, "b": bucket}, sort_keys=True, default=str)
    return "auto-" + hashlib.sha256(raw.encode()).hexdigest()[:32]


async def run_tool(
    tc: ToolContext, *, tool: str, source: str, op: Op, model: type[M], mapper: Callable[[Any], M],
    scopes: tuple[str, ...] = (READ,), path: Mapping[str, str] | None = None, query: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None, write: bool = False, compute: bool = False,
    idempotency_key: str | None = None, log_refs: Mapping[str, str | None] | None = None,
    precheck: Callable[[], None] | None = None,
) -> Envelope[M]:
    """`write`: transactional (gated by feature flag + trc.write). `compute`: non-destructive POST that records a run
    on-prem (idempotency key attached, not gated by the write flag)."""
    started = time.perf_counter()
    request_id = uuid.uuid4().hex
    env_t = Envelope[model]  # type: ignore[valid-type]

    def meta(key: str | None = None) -> Meta:
        return Meta(request_id=request_id, tool=tool, source_system=source, as_of=datetime.now(timezone.utc),
                    latency_ms=int((time.perf_counter() - started) * 1000), idempotency_key=key, read_only=not (write or compute))

    key = idempotency_key
    refs = {k: phi_ref(v) for k, v in (log_refs or {}).items()}
    try:
        principal = tc.principal_resolver()
        request_id = principal.correlation_id  # one correlation id end-to-end: GWChat -> agent -> Gateway -> MCP -> on-prem
        principal.require(*scopes)
        if precheck:
            precheck()
        if write and not tc.settings.write_tools_enabled:
            raise OnPremError(ErrorCode.FORBIDDEN, "Transactional tools are disabled in this environment.")
        if (write or compute) and not key:
            key = derive_idempotency_key(principal, tool, body or {})
        ctx = CallContext(principal=principal, request_id=request_id, tool=tool, idempotency_key=key)
        raw = await tc.client.call(op, ctx=ctx, path=path, query=query, body=body)
        data = mapper(raw)
        log.info("tool_ok", tool=tool, request_id=request_id, user=phi_ref(principal.user_id), **refs,
                 latency_ms=int((time.perf_counter() - started) * 1000))
        return env_t(ok=True, data=data, meta=meta(key))
    except OnPremError as exc:
        failure = exc.to_failure()
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        # Never include the offending payload: it may contain PHI.
        failure = ToolFailure(code=ErrorCode.UPSTREAM_SCHEMA_MISMATCH,
                              message="Upstream response did not match the expected contract.",
                              details={"error_type": type(exc).__name__})
    except Exception as exc:  # noqa: BLE001
        log.exception("tool_internal_error", tool=tool, request_id=request_id)
        failure = ToolFailure(code=ErrorCode.INTERNAL, message="Internal error.", details={"error_type": type(exc).__name__})
    log.warning("tool_failed", tool=tool, request_id=request_id, code=failure.code.value, retryable=failure.retryable, **refs)
    return env_t(ok=False, error=failure, meta=meta(key))
