"""Builds gwchat_ui/frontend/index.html from the approved mockup (reference/GuideWellChat_TRC_HEDIS_Prototype_Draft.html).

The mockup's <style> block and its shell markup (sidebar, welcome screen, chat screen, composer, model picker) are copied VERBATIM so the look
is identical. Only three things change: the scripted demo hooks are re-pointed to the live app (frontend/app.js), the composer is enabled for
free typing, and a few extra elements (settings dialog, flow drawer) are appended. Extra CSS lives in frontend/extra.css.

    python tools/build_component.py [path/to/mockup.html]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "gwchat_ui" / "frontend"
SRCDIR = ROOT / "frontend_src"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reference" / "GuideWellChat_TRC_HEDIS_Prototype_Draft.html"

html = SRC.read_text(encoding="utf-8")

css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
shell = re.search(r'(<div class="app-wrapper">.*?</div><!-- end \.app-wrapper -->)', html, re.S).group(1)

# --- re-point scripted-demo hooks to the live app -------------------------------------------------------------------------------------------
shell = shell.replace('onclick="showWelcome()"', 'onclick="GW.newChat()"').replace('onclick="startTRCDemo()"', 'onclick="GW.newChat()"')
shell = shell.replace('onclick="handleWelcomeSend()"', 'onclick="GW.sendFromWelcome()"').replace('onclick="handleChatSend()"', 'onclick="GW.sendFromChat()"')
# composer: free typing (the mockup locks it to the scripted prompts)
shell = shell.replace('<textarea placeholder="Reply..." id="chat-input" rows="1" readonly></textarea>', '<textarea placeholder="Reply..." id="chat-input" rows="1"></textarea>')
shell = shell.replace('<div class="input-bar disabled" id="chat-input-bar">', '<div class="input-bar" id="chat-input-bar">')
# footer text: this build talks to a real agent
shell = shell.replace("GuideWell Chat · TRC HEDIS Prototype · Illustrative mock data only, not real member information · Generated content may be inaccurate or false.",
                      "GuideWell Chat · TRC HEDIS · Answers are built from tool results only; nothing is inferred · Generated content may be inaccurate.")
# user menu: Settings opens the connection dialog; the other items stay as in the mockup
shell = shell.replace('<div class="user-menu-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/>',
                      '<div class="user-menu-item" onclick="GW.openSettings()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/>', 1)
# chat title bar: add the flow button
shell = shell.replace('<div class="chat-title-bar-inner">', '<div class="chat-title-bar-inner">', 1)
shell = shell.replace('''      </button>
    </div>
  </div>
  <div class="chat-area" id="chat-area">''', '''      </button>
      <button class="flow-btn" id="flow-btn" onclick="GW.openFlow()" title="Show how this answer travelled: UI → Agent → Gateway → MCP → on-prem">⇄ Flow</button>
    </div>
  </div>
  <div class="chat-area" id="chat-area">''', 1)
extra_css = (SRCDIR / "extra.css").read_text(encoding="utf-8")
extra_html = (SRCDIR / "extra.html").read_text(encoding="utf-8")

out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GuideWell Chat</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="chart.umd.js"></script>
<style>{css}</style>
<style>/* ---- additions for the live (non-scripted) build ---- */
{extra_css}</style>
</head>
<body>
{shell}
{extra_html}
<script src="app.js"></script>
</body>
</html>
"""
(FRONT / "index.html").write_text(out, encoding="utf-8")
core = (SRCDIR / "app.core.js").read_text(encoding="utf-8")
parts = "\n".join((SRCDIR / n).read_text(encoding="utf-8") for n in ("renderers.js", "panels.js", "chrome.js"))
assert "/* __PART2__ */" in core
(FRONT / "app.js").write_text(core.replace("/* __PART2__ */", parts), encoding="utf-8")
print("wrote", FRONT / "index.html", len(out), "bytes")
