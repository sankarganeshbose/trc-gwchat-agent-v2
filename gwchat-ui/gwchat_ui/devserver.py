"""Standalone host for the same page (no Streamlit): serves gwchat_ui/frontend and POST /api/chat → Bridge → agent.
Useful for quick UI work and for automated browser tests; the Streamlit app (app.py) is the supported way to present it.

    python -m gwchat_ui.devserver            # http://localhost:8600
"""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .bridge_core import Bridge

FRONT = Path(__file__).parent / "frontend"


def make_app(bridge: Bridge | None = None) -> Starlette:
    b = bridge or Bridge(url=os.getenv("GWCHAT_AGENT_URL", "http://localhost:8080/invocations"), token=os.getenv("GWCHAT_AGENT_TOKEN", ""),
                         user_id=os.getenv("GWCHAT_USER_ID", "sankar.bose"))

    async def chat(request: Request):
        import anyio
        req = await request.json()
        return JSONResponse(await anyio.to_thread.run_sync(b.handle, req))

    async def config(_: Request):
        return JSONResponse({"url": b.url, "token_set": bool(b.token)})

    return Starlette(routes=[Route("/api/chat", chat, methods=["POST"]), Route("/api/config", config),
                             Mount("/", StaticFiles(directory=FRONT, html=True), name="ui")])


if __name__ == "__main__":
    uvicorn.run(make_app(), host="127.0.0.1", port=int(os.getenv("UI_PORT", "8600")), log_level="warning")
