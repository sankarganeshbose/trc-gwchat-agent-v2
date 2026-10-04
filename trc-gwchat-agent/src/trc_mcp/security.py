"""Inbound identity for the MCP server.

AgentCore Gateway authenticates the *caller* (agent) with its inbound JWT authorizer and then calls this server using
its configured outbound auth. ASSUMPTION: end-user identity reaches this server either as a token-exchanged JWT
(Gateway TOKEN_EXCHANGE / OBO) in `Authorization`, or as an allow-listed header (`x-gw-user-id`).
The server does NOT re-verify signatures when `trust_upstream_jwt` is on because the AgentCore authorizer in front of
it already did; deploy it only behind Gateway/Runtime (private target, no public ingress).
"""
from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field

from trc_contracts.common import ErrorCode

from .config import Settings
from .errors import OnPremError

READ = "trc.read"
WRITE = "trc.write"
RECORDS = "trc.records.read"
ALL_SCOPES = frozenset({READ, WRITE, RECORDS})


@dataclass(frozen=True)
class Principal:
    user_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def require(self, *scopes: str) -> None:
        missing = [s for s in scopes if s not in self.scopes]
        if missing:
            raise OnPremError(ErrorCode.FORBIDDEN, f"Missing required scope(s): {', '.join(missing)}")


def _claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception as exc:  # noqa: BLE001
        raise OnPremError(ErrorCode.UNAUTHENTICATED, "Malformed bearer token.") from exc


def principal_from_headers(headers: dict[str, str], settings: Settings) -> Principal:
    h = {k.lower(): v for k, v in headers.items()}
    corr = h.get("x-correlation-id") or uuid.uuid4().hex
    auth = h.get("authorization", "")
    if auth.lower().startswith("bearer ") and settings.trust_upstream_jwt:
        claims = _claims(auth[7:])
        raw = claims.get("scp") or claims.get("scope") or ""
        scopes = frozenset(raw.split() if isinstance(raw, str) else raw)
        user = claims.get("preferred_username") or claims.get("upn") or claims.get("sub")
        if not user:
            raise OnPremError(ErrorCode.UNAUTHENTICATED, "Token has no user identity.")
        return Principal(user_id=str(user), scopes=scopes, correlation_id=corr)
    if h.get(settings.user_header):
        # Header-forwarded identity: scopes must come from a trusted header too, otherwise read-only.
        scopes = frozenset((h.get("x-gw-scopes") or READ).split())
        return Principal(user_id=h[settings.user_header], scopes=scopes, correlation_id=corr)
    if not settings.require_auth:
        return Principal(user_id="dev-user", scopes=ALL_SCOPES, correlation_id=corr)
    raise OnPremError(ErrorCode.UNAUTHENTICATED, "No end-user identity on request.")
