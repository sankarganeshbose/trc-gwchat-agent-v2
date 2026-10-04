#!/usr/bin/env bash
# UI only (point GWCHAT_AGENT_URL at any agent). For the full local demo use run_demo.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
python -m streamlit run app.py --server.port "${UI_PORT:-8501}"
