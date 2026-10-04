#!/usr/bin/env bash
# Starts the demo backend (agent :8080, MCP server :8000) and the Streamlit UI (:8501). Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD" DEMO_PORT="${DEMO_PORT:-8080}" DEMO_MCP_PORT="${DEMO_MCP_PORT:-8000}"
export GWCHAT_AGENT_URL="http://localhost:${DEMO_PORT}/invocations"
python3 -m demo_backend.server & BACKEND=$!
trap 'kill $BACKEND 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do curl -fs "http://localhost:${DEMO_PORT}/ping" >/dev/null && break; sleep 0.5; done
python3 -m streamlit run app.py --server.port "${UI_PORT:-8501}"
