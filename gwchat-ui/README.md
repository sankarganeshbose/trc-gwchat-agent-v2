# GWChat UI (TRC) — mockup-faithful front end for the GWChat Integration Agent

This is the GuideWell Chat UI from `GuideWellChat_TRC_HEDIS_Prototype_Draft.html`, connected to the **real agent**:

```
Browser page (your mockup)  ─▶  Streamlit (Python, holds the token)  ─▶  Agent (AgentCore Runtime /invocations)
                                                                      ─▶  AgentCore Gateway ─▶ FastMCP tools ─▶ on-prem REST API
```

## What is the mockup and what is live

| Mockup | This build |
|---|---|
| `<style>` block, sidebar, welcome screen, chat screen, composer, model picker, user menu | **Copied verbatim** by `tools/build_component.py` (a test asserts the CSS is byte-identical) |
| Scripted `TURNS` playback with a locked composer | Removed. You type any question; it goes to the agent |
| Hard-coded `MEMBERS`, charts, KPIs | Removed. Every number, name and status is drawn from the agent's typed **blocks** (tool results) |
| "Connecting to GuideWell data sources" trace | Same card, filled from the real `tool_trace` (tool names, latencies, on-prem routes in the demo) |
| Dashboard, worklist cards/table, member record (7 tabs), notifications, closure board, validation, records | Same components, rendered per block type (`frontend_src/renderers.js`, `panels.js`) |
| (not in mockup) | Approve/Reject cards for writes, data-gap cards, "⇄ Flow" drawer showing UI → Agent → Gateway → MCP → on-prem, Settings dialog |

Where a tool cannot supply data the page says so ("Not available… nothing has been inferred"). The mockup's **model picker is cosmetic** here: the model is set on the agent (`TRC_AGENT_MODEL_ID`). **Line of Business** on the dashboard filter bar is disabled because no tool filters by it.

## Run it

```bash
cd gwchat-ui
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-demo.txt          # UI + local demo backend (real agent + real FastMCP, keyword stand-in for Bedrock)
bash scripts/run_demo.sh                       # backend :8080/:8000 and the UI on http://localhost:8501
```

Against a deployed agent instead: `export GWCHAT_AGENT_URL=https://…/invocations` (and put the bearer token in **Settings** or `GWCHAT_AGENT_TOKEN`), then `bash scripts/run_ui.sh`.

Without Streamlit (same page, quick UI work): `python -m gwchat_ui.devserver` → http://localhost:8600.

Fonts load from Google Fonts and Chart.js is vendored (`gwchat_ui/frontend/chart.umd.js`), so the page works offline apart from the font.

## Try these (they mirror the mockup's flow)

1. *How are we doing on TRC? Show the dashboard.* — one parallel fan-out: summary, four breakdowns, top no-upload members.
2. *Show members discharged in the last 14 days where the provider has not uploaded documents by day 3, ranked by risk* — worklist; filter client-side; click a card.
3. *Open the TRC record for HCC-4471829* — 13 parallel reads, seven tabs.
4. *Which providers have not acknowledged their TRC discharge notifications?* → *Bulk resend…* → Approve.
5. *Run the validation agent and show the closure board* → "Soft close…" on a passed member → Approve.
6. *Close HCC-3345510 in MRAT* — refused (human-only). *Show the TRC status for HCC-0000000* — "not available".

Use **⇄ Flow** (title bar) or the link under any answer to show how that answer travelled. Settings (user menu) → **Reset demo data** restores the stub's in-memory data.

## Test everything

```bash
pytest                                   # 17 tests: router, flow, backend, bridge, dev server, build fidelity
bash scripts/run_demo.sh &               # then, in another shell:
pip install playwright && playwright install chromium
python scripts/e2e_browser.py            # 33 browser checks through the real Streamlit page
```

## Layout

```
app.py                      Streamlit host (full-bleed component; calls the agent server-side)
gwchat_ui/bridge_core.py    request kinds: message | confirm | new_chat | ping | reset_demo | configure
gwchat_ui/component.py      declares the bidirectional component
gwchat_ui/frontend/         GENERATED page (index.html, app.js) + vendored chart.umd.js
frontend_src/               app.core.js, renderers.js, panels.js, chrome.js, extra.css, extra.html
tools/build_component.py    rebuilds frontend/ from reference/<mockup>.html — rerun after editing frontend_src/
reference/                  the approved mockup (source of the CSS/markup)
demo_backend/               local stand-in for AgentCore Runtime (real agent + MCP, keyword router)
tests/                      pytest (16): router, flow, backend, bridge, dev server, build fidelity
```

After editing `frontend_src/*`: `python tools/build_component.py` (a test fails if the generated files are stale).

## Notes

* The browser never sees the bearer token after you save it; it lives in the Streamlit process.
* Approve/Reject only relays the agent-signed ticket; the agent enforces user/session/tool/argument binding, expiry and one-time use.
* The `_demo` field (on-prem routes/timings) exists only on the demo backend; a real agent doesn't return it and the flow drawer then shows generic on-prem text.
