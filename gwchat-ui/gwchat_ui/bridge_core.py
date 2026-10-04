"""Server-side half of the GWChat UI. The browser page never sees the bearer token or calls the agent itself: it hands a small request dict
to Python (Streamlit component value, or POST /api/chat in the dev server) and Python calls the agent, then returns a payload for the page to draw.

request kinds : message | confirm | new_chat | ping | reset_demo | configure
payload       : {nonce, kind, ok, error, reply, http_ms, steps, demo, detail}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import AgentClient, new_session_id
from .flow import build_steps


@dataclass
class Bridge:
    url: str
    token: str = ""
    user_id: str = "sankar.bose"
    session_id: str = field(default_factory=new_session_id)

    def client(self) -> AgentClient:
        return AgentClient(self.url, self.token or None)

    def handle(self, req: dict[str, Any]) -> dict[str, Any]:
        kind, nonce = req.get("kind"), req.get("nonce")
        base: dict[str, Any] = {"nonce": nonce, "kind": kind, "ok": True, "error": None}
        if kind == "new_chat":
            self.session_id = new_session_id()
            return {**base, "detail": "new session"}
        if kind == "configure":
            if req.get("url"):
                self.url = str(req["url"]).strip()
            if "token" in req and req["token"] is not None:
                self.token = str(req["token"]).strip()
            return {**base, "detail": "saved", "url": self.url, "token_set": bool(self.token)}
        if kind == "ping":
            ok, detail = self.client().ping()
            return {**base, "ok": ok, "detail": detail, "url": self.url, "token_set": bool(self.token)}
        if kind == "reset_demo":
            ok, detail = self.client().reset_demo()
            return {**base, "ok": ok, "detail": detail}
        if kind in ("message", "confirm"):
            c = self.client()
            if kind == "confirm":
                reply = c.send(session_id=self.session_id, user_id=self.user_id,
                               confirmation={"ticket": req.get("ticket"), "decision": req.get("decision")},
                               selected_member_id=req.get("selected_member_id"))
            else:
                reply = c.send(session_id=self.session_id, user_id=self.user_id, message=str(req.get("message", ""))[:4000],
                               selected_member_id=req.get("selected_member_id"))
            if not reply.ok:
                return {**base, "ok": False, "error": reply.error, "http_ms": reply.http_ms, "reply": None, "steps": []}
            demo = reply.data.get("_demo")
            return {**base, "reply": {k: v for k, v in reply.data.items() if k != "_demo"}, "http_ms": reply.http_ms,
                    "steps": build_steps(reply), "demo": demo}
        return {**base, "ok": False, "error": f"unknown request kind: {kind}"}
