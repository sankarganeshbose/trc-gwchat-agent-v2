"""Stateless human-confirmation tickets (HMAC-signed). No server-side session state => request-scoped, restart-safe.

Flow: LLM proposes a write -> hook cancels the tool call and issues a ticket -> GWChat shows the summary and asks the user ->
user clicks Approve -> GWChat sends {confirmation:{ticket,decision}} -> the agent VERIFIES the ticket (signature, expiry, same user and
session) and executes the exact signed tool+arguments deterministically (no LLM in the loop).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..models.schemas import PendingAction


class TicketError(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass(frozen=True)
class VerifiedTicket:
    tool: str
    args: dict[str, Any]
    idempotency_key: str


def summarize(tool: str, args: dict[str, Any]) -> str:
    """Deterministic, human-readable description of the exact action (shown to the user for approval)."""
    a = args
    if tool == "send_provider_notification":
        return f"Resend the TRC provider alert for member {a.get('member_id')} via {a.get('channel') or 'the original channel'}."
    if tool == "resend_notifications_bulk":
        ids = a.get("member_ids") or []
        return f"Resend TRC provider alerts for {len(ids)} member(s): {', '.join(ids[:10])}{'…' if len(ids) > 10 else ''}."
    if tool == "escalate_to_provider_manager":
        return f"Escalate member {a.get('member_id')}'s provider notification to the Provider Manager."
    if tool == "log_intervention_activity":
        return f"Log an intervention activity for member {a.get('member_id')}: “{a.get('activity')}”."
    if tool == "update_review_status":
        return f"Soft-close the TRC task for member {a.get('member_id')} (routes to MRAT for HEDIS-nurse final closure)."
    if tool == "request_worklist_export":
        return f"Create a {a.get('format')} export of the filtered TRC worklist (generated on-prem)."
    return f"Run {tool}."


class TicketSigner:
    def __init__(self, secret: str, ttl_s: int):
        self._key, self._ttl = secret.encode(), ttl_s

    def _sig(self, body: str) -> str:
        return _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())

    def issue(self, *, user_id: str, session_id: str, tool: str, args: dict[str, Any]) -> PendingAction:
        exp = int(time.time()) + self._ttl
        body = _b64(json.dumps({"u": user_id, "s": session_id, "t": tool, "a": args, "x": exp, "n": uuid.uuid4().hex[:12]},
                               sort_keys=True, separators=(",", ":")).encode())
        return PendingAction(ticket=f"{body}.{self._sig(body)}", tool=tool, summary=summarize(tool, args), arguments=args,
                             expires_at=datetime.fromtimestamp(exp, tz=timezone.utc))

    def verify(self, ticket: str, *, user_id: str, session_id: str) -> VerifiedTicket:
        try:
            body, sig = ticket.rsplit(".", 1)
        except ValueError as exc:
            raise TicketError("Malformed confirmation ticket.") from exc
        if not hmac.compare_digest(sig, self._sig(body)):
            raise TicketError("Confirmation ticket failed verification.")
        p = json.loads(_unb64(body))
        if p["x"] < time.time():
            raise TicketError("Confirmation ticket has expired. Please request the action again.")
        if p["u"] != user_id or p["s"] != session_id:
            raise TicketError("Confirmation ticket does not belong to this user/session.")
        # Same ticket => same idempotency key => replays (double-click, retry) can never double-send.
        return VerifiedTicket(tool=p["t"], args=p["a"], idempotency_key="tk-" + hashlib.sha256(ticket.encode()).hexdigest()[:40])
