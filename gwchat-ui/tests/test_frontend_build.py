"""The page must stay the mockup: its CSS and shell are copied verbatim by tools/build_component.py."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOCK = (ROOT / "reference" / "GuideWellChat_TRC_HEDIS_Prototype_Draft.html").read_text(encoding="utf-8")
PAGE = (ROOT / "gwchat_ui" / "frontend" / "index.html").read_text(encoding="utf-8")


def test_mockup_css_is_embedded_verbatim():
    css = re.search(r"<style>(.*?)</style>", MOCK, re.S).group(1)
    assert css in PAGE


def test_shell_ids_from_the_mockup_survive():
    for i in ("welcome-screen", "chat-screen", "chat-messages", "typing-indicator", "chat-input-bar", "welcome-model-badge", "user-menu"):
        assert f'id="{i}"' in PAGE
    assert "Welcome back" in PAGE and "TRC Measure Gap Review" in PAGE
    assert "readonly></textarea>" not in PAGE.split('id="chat-input"')[1][:80]       # composer is free-typing


def test_built_files_are_current():
    before = (ROOT / "gwchat_ui" / "frontend" / "app.js").read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_component.py")], check=True, capture_output=True)
    assert (ROOT / "gwchat_ui" / "frontend" / "app.js").read_text(encoding="utf-8") == before


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_app_js_parses():
    subprocess.run(["node", "--check", str(ROOT / "gwchat_ui" / "frontend" / "app.js")], check=True)
