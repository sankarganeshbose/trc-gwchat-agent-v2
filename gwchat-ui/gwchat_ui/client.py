"""HTTP client the GWChat UI uses to reach the agent. In production the same call goes to the AgentCore Runtime invocation URL
(with the user's Entra ID bearer token and a runtime-session-id header); locally it goes to the demo backend."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


def new_session_id() -> str:
    # AgentCore Runtime session ids are expected to be long (VERIFY min length); a 39-char id is safe.
    return "gwchat-" + uuid.uuid4().hex


@dataclass
class AgentReply:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    http_status: int | None = None
    http_ms: int = 0
    request_body: dict[str, Any] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None


class AgentClient:
    def __init__(self, url: str, token: str | None = None, timeout_s: float = 120.0):
        self.url, self.token, self.timeout_s = url.rstrip("/"), (token or "").strip() or None, timeout_s

    # ── helpers ──
    def _headers(self, session_id: str) -> dict[str, str]:
        h = {"Content-Type": "application/json", "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    @staticmethod
    def redact(headers: dict[str, str]) -> dict[str, str]:
        return {k: ("Bearer ***redacted***" if k.lower() == "authorization" else v) for k, v in headers.items()}

    def ping(self) -> tuple[bool, str]:
        try:
            r = httpx.get(self.url.rsplit("/invocations", 1)[0] + "/ping", timeout=5.0, headers={"Authorization": f"Bearer {self.token}"} if self.token else None)
            return r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        except httpx.HTTPError as exc:
            return False, f"{type(exc).__name__}: {exc}"

    def reset_demo(self) -> tuple[bool, str]:
        """Demo backend only: POST /demo/reset restores the stub on-prem data."""
        try:
            r = httpx.post(self.url.rsplit("/invocations", 1)[0] + "/demo/reset", timeout=5.0)
            return r.status_code == 200, f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            return False, f"{type(exc).__name__}: {exc}"

    # ── main call ──
    def send(self, *, session_id: str, user_id: str, message: str | None = None, confirmation: dict | None = None,
             selected_member_id: str | None = None, active_filters: dict | None = None) -> AgentReply:
        body: dict[str, Any] = {"session_id": session_id, "user_id": user_id,
                                "context": {"selected_member_id": selected_member_id or None, "active_filters": active_filters or {}}}
        if confirmation:
            body["confirmation"] = confirmation
        else:
            body["message"] = message
        headers = self._headers(session_id)
        t = time.perf_counter()
        try:
            r = httpx.post(self.url, json=body, headers=headers, timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            return AgentReply(False, request_body=body, request_headers=self.redact(headers), error=f"Could not reach the agent ({type(exc).__name__}). Is it running at {self.url}?")
        ms = int((time.perf_counter() - t) * 1000)
        if r.status_code != 200:
            return AgentReply(False, http_status=r.status_code, http_ms=ms, request_body=body, request_headers=self.redact(headers),
                              error=f"Agent returned HTTP {r.status_code}: {r.text[:300]}")
        try:
            data = r.json()
        except ValueError:
            return AgentReply(False, http_status=200, http_ms=ms, request_body=body, request_headers=self.redact(headers), error="Agent returned a non-JSON body.")
        return AgentReply(True, data=data, http_status=200, http_ms=ms, request_body=body, request_headers=self.redact(headers))
