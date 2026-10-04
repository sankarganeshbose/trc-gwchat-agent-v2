"""GuideWell Chat (TRC) — Streamlit host for the mockup-faithful UI.

    streamlit run app.py

The page itself (gwchat_ui/frontend) is the approved mockup's HTML/CSS shell with live renderers. Streamlit's job here is the server side:
it receives each request from the page, calls the GWChat Integration Agent (AgentCore Runtime /invocations) with the bearer token that only
this process holds, and hands the reply back to the page.
"""
from __future__ import annotations

import os

import streamlit as st

from gwchat_ui.bridge_core import Bridge
from gwchat_ui.component import gwchat

st.set_page_config(page_title="GuideWell Chat", page_icon="💬", layout="wide", initial_sidebar_state="collapsed")

# Full-bleed: the component iframe fills the browser window; Streamlit chrome is hidden.
st.markdown("""<style>
html,body,.stApp{overflow:hidden!important;background:#fafafa}
header,[data-testid="stToolbar"],[data-testid="stStatusWidget"],[data-testid="stDecoration"],footer,[data-testid="stSidebar"],[data-testid="collapsedControl"]{display:none!important}
.block-container,[data-testid="stMainBlockContainer"]{padding:0!important;max-width:100%!important}
iframe[title*="gwchat_mockup"]{position:fixed;inset:0;width:100vw;height:100vh;border:0;z-index:100}
</style>""", unsafe_allow_html=True)

if "bridge" not in st.session_state:
    st.session_state.bridge = Bridge(url=os.getenv("GWCHAT_AGENT_URL", "http://localhost:8080/invocations"),
                                     token=os.getenv("GWCHAT_AGENT_TOKEN", ""), user_id=os.getenv("GWCHAT_USER_ID", "sankar.bose"))
    st.session_state.payload, st.session_state.last_nonce = None, None
bridge: Bridge = st.session_state.bridge

req = gwchat(payload=st.session_state.payload, config={"url": bridge.url, "token_set": bool(bridge.token)})
if req and req.get("nonce") != st.session_state.last_nonce:
    st.session_state.last_nonce = req["nonce"]
    st.session_state.payload = bridge.handle(req)  # blocking call to the agent; the page shows its typing indicator meanwhile
    st.rerun()
