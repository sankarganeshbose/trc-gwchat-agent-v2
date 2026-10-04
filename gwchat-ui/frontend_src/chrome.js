  /* ───────────── welcome suggestions (the mockup's own demo questions, reworded to what the agent's tools can answer) ───────────── */
  var WELCOME_RECS = [
    'How are we doing on TRC? Show the dashboard.',
    'Show members discharged in the last 14 days where the provider has not uploaded documents by day 3, ranked by risk',
    'Open the TRC record for HCC-4471829',
    'Which providers have not acknowledged their TRC discharge notifications?',
    'Run the validation agent and show the closure board',
    'Show attachments for HCC-4471829'
  ];
  function buildWelcomeRecs() {
    var ws = $('welcome-screen'); if (!ws || $('welcome-recs')) return;
    var d = document.createElement('div'); d.className = 'welcome-recs prompt-recs'; d.id = 'welcome-recs';
    d.innerHTML = WELCOME_RECS.map(function (q, k) { return '<button class="prompt-rec ' + (k ? 'secondary' : 'primary') + '" data-act="ask" data-q="' + Aq(q) + '">' + ARROW + E(q.length > 70 ? q.slice(0, 68) + '…' : q) + '</button>'; }).join('');
    ws.appendChild(d);
  }

  /* ───────────── flow drawer: the demo of UI → Agent → Gateway → MCP → on-prem for one answer ───────────── */
  function openOverlay(id) { $('gw-scrim').classList.add('open'); $(id).classList.add('open'); }
  function closeOverlays() { $('gw-scrim').classList.remove('open'); $('settings-dialog').classList.remove('open'); $('flow-drawer').classList.remove('open'); }
  GW.closeOverlays = closeOverlays;
  GW.openFlow = function (idx) {
    if (idx === undefined || isNaN(idx)) idx = S.replies.length - 1;
    var r = S.replies[idx];
    if (!r) { toast('Ask a question first — the flow is drawn for a specific answer.'); return; }
    var p = r.payload, rp = p.reply, demo = p.demo || {}, tr = rp.tool_trace || [], onprem = demo.onprem_calls || [];
    var called = tr.filter(function (t) { return t.outcome !== 'queued_for_confirmation' && t.outcome !== 'blocked'; });
    var held = tr.filter(function (t) { return t.outcome === 'queued_for_confirmation'; }), blocked = tr.filter(function (t) { return t.outcome === 'blocked'; });
    var h = '<div class="fd-q"><b>Question:</b> ' + E(r.question) + '</div><div class="fd-lane">';
    h += '<div class="fd-node ui"><b>GWChat UI</b><small>POST /invocations · prompt + UI context + bearer token · ' + E(p.http_ms) + ' ms round trip</small></div><div class="fd-arrow">▼ HTTPS (AgentCore Runtime invocation)</div>';
    h += '<div class="fd-node"><b>Agent — AgentCore Runtime (Strands + LLM)</b><small>Intent: ' + E(rp.intent) + ' · offered only allow-listed tools · ' + E(demo.llm || 'Bedrock model') + '</small></div>';
    if (held.length || blocked.length) {
      h += '<div class="fd-arrow">▼ write guardrail</div><div class="fd-node guard"><b>Write interception</b><small>' + held.map(function (t) { return E(t.tool) + ' held — signed confirmation ticket issued, nothing sent to the Gateway'; }).join('<br>') + blocked.map(function (t) { return '<br>' + E(t.tool) + ' blocked (' + E(t.error_code) + ')'; }).join('') + '</small></div>';
    }
    if (called.length) {
      h += '<div class="fd-arrow">▼ MCP tools/call × ' + called.length + (called.length > 1 ? ' (parallel where independent)' : '') + '</div>';
      h += '<div class="fd-node"><b>AgentCore Gateway</b><small>' + E(demo.gateway || 'authn/z, tool routing, policy') + '</small></div><div class="fd-arrow">▼</div>';
      h += '<div class="fd-node"><b>FastMCP server — typed tools</b><div class="fd-tools">' + called.map(function (t) { return '<span class="fd-chip' + (t.ok ? '' : ' fail') + '">' + E(t.tool) + ' · ' + nz(t.latency_ms, '-') + ' ms</span>'; }).join('') + '</div></div><div class="fd-arrow">▼ REST (read-only unless a write was approved)</div>';
      var routes = onprem.length ? onprem.map(function (o) { return E(o.method + ' ' + o.route) + ' · ' + o.ms + ' ms'; }).join('<br>') : 'GuideWell on-prem TRC REST API (CareNavi · ADT/HIE · Vista · EIP · Claims · MRAT)';
      h += '<div class="fd-node onprem"><b>On-prem TRC API</b><small>' + routes + '</small></div>';
    } else if (!held.length) {
      h += '<div class="fd-arrow">▼</div><div class="fd-node"><b>No tool call</b><small>Clarification, out-of-scope or capability answer — nothing was looked up or inferred.</small></div>';
    }
    h += '<div class="fd-arrow">▲ blocks built verbatim from tool data</div><div class="fd-node ui"><b>Back to GWChat UI</b><small>status ' + E(rp.status) + ' · ' + (rp.blocks || []).length + ' block(s) · ' + (rp.data_gaps || []).length + ' data gap(s)</small></div></div>';
    h += '<table class="fd-table"><tr><th>#</th><th>Hop</th><th>What happened</th><th>ms</th></tr>' + (p.steps || []).map(function (s) { return '<tr><td>' + s['#'] + '</td><td><b>' + E(s.Hop) + '</b><br><span style="color:#64748b">' + E(s.Component) + '</span></td><td>' + E(s['What happened']) + '</td><td>' + nz(s.ms, '') + '</td></tr>'; }).join('') + '</table>';
    $('fd-body').innerHTML = h;
    $('fd-meta').textContent = demo.agent_ms !== undefined ? 'Agent time ' + demo.agent_ms + ' ms · demo backend (Gateway bypassed, keyword LLM stand-in)' : 'Live agent';
    openOverlay('flow-drawer');
  };

  /* ───────────── settings ───────────── */
  GW.openSettings = function () {
    $('user-menu').classList.remove('open');
    $('set-url').value = S.cfg.url || ''; $('set-token').value = ''; $('set-token').placeholder = S.cfg.token_set ? 'a token is set — leave blank to keep it' : 'optional locally';
    $('set-status').textContent = ''; openOverlay('settings-dialog');
  };
  function setStatus(t, bad) { var s = $('set-status'); s.textContent = t; s.style.color = bad ? '#b42318' : '#2b7a4b'; }
  GW.settingsSave = function () {
    var req = { kind: 'configure', url: $('set-url').value.trim() }; var tk = $('set-token').value; if (tk) req.token = tk;
    transport(req).then(function (p) { if (p.ok) { S.cfg.url = p.url || req.url; S.cfg.token_set = !!p.token_set; $('set-token').value = ''; setStatus('Saved.'); } else setStatus(p.error || 'Could not save', true); });
  };
  GW.settingsTest = function () { setStatus('Testing...'); transport({ kind: 'ping' }).then(function (p) { setStatus(p.ok ? 'Reachable — ' + (p.detail || 'ok') : 'Not reachable — ' + (p.detail || p.error || ''), !p.ok); }); };
  GW.settingsReset = function () { setStatus('Resetting...'); transport({ kind: 'reset_demo' }).then(function (p) { setStatus(p.ok ? 'Demo data restored.' : 'Not a demo backend (' + (p.detail || p.error || '') + ')', !p.ok); }); };
