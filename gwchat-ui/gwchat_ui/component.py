"""Declares the GWChat page (gwchat_ui/frontend) as a bidirectional Streamlit component."""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_gwchat = components.declare_component("gwchat_mockup", path=str(Path(__file__).parent / "frontend"))


def gwchat(*, payload: dict | None, config: dict, key: str = "gwchat"):
    """Renders the page. Returns the latest request dict the page sent (or None); `payload` is Python's answer to a previous request."""
    return _gwchat(payload=payload, config=config, key=key, default=None)
