/* GuideWell Chat — live front end.
 *
 * The shell (sidebar, welcome screen, chat screen, composer, model picker, user menu) and every CSS rule come from the approved mockup.
 * What changed: the scripted TURNS playback is gone. Every question goes to the real GWChat Integration Agent (via the Python bridge), and
 * the reply's typed blocks are drawn with the mockup's own components (KPI cards, member cards, ADT timeline, kanban, ...).
 * Nothing on screen is invented here: every number, name and status comes from a tool result. Where a tool could not supply data
 * the page says so (see unavailable()/gapsCard()).
 *
 * Transport: inside Streamlit this page is a bidirectional component (postMessage protocol, plain JS, no build step). Opened directly via the
 * dev server it POSTs to /api/chat. Either way the bearer token stays in Python.
 */
(function () {
  'use strict';
  var GW = (window.GW = {});

  /* ───────────── small helpers ───────────── */
  function $(id) { return document.getElementById(id); }
  function E(s) { return s === null || s === undefined ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function Aq(s) { return E(s).replace(/'/g, '&#39;'); }
  function T(s) { return E(String(s === null || s === undefined ? '' : s).replace(/_/g, ' ')); }
  function nz(v, d) { return v === null || v === undefined || v === '' ? (d === undefined ? '—' : d) : v; }
  function num(n) { return typeof n === 'number' ? n.toLocaleString('en-US') : E(nz(n)); }
  function pct(v) { return v === null || v === undefined ? '—' : (Math.round(v * 10) / 10) + '%'; }
  function D(iso) {
    if (!iso) return '—';
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return m ? m[2] + '/' + m[3] + '/' + m[1] : E(iso);
  }
  function DT(iso) {
    if (!iso) return '—';
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso);
    return m ? m[2] + '/' + m[3] + '/' + m[1] + ' ' + m[4] + ':' + m[5] : D(iso);
  }
  function TM(iso) { var m = /[T ](\d{2}:\d{2})/.exec(iso || ''); return m ? m[1] : ''; }
  function first(s, sep) { return String(s || '').split(sep || ' — ')[0]; }
  function norm(s) { return String(s || '').toUpperCase().replace(/[\s_]+/g, '_'); }
  function toast(msg) { var t = $('gw-toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove('show'); }, 2600); }
  var CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
  var CROSS = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  var HOLD = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>';
  var DB = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4.03 3-9 3S3 13.66 3 12"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/></svg>';
  var CHEV = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
  var ARROW = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';

  /* ───────────── badges (same palette/rules as the mockup) ───────────── */
  function badge(cls, t) { return '<span class="badge ' + cls + '">' + E(t) + '</span>'; }
  function riskBadge(t) { t = norm(t); return t === 'HIGH' ? badge('badge-red', 'HIGH RISK') : t === 'MEDIUM' ? badge('badge-amber', 'MEDIUM RISK') : t === 'LOW' ? badge('badge-green', 'LOW RISK') : badge('badge-gray', 'RISK N/A'); }
  var TRC_CLS = { DISCHARGE_IDENTIFIED: 'badge-red', PROVIDER_NOTIFIED: 'badge-amber', VALIDATION_PASSED: 'badge-blue', SOFT_CLOSED: 'badge-green', MRAT_CLOSED: 'badge-green', EXCLUDED: 'badge-gray' };
  function trcBadge(s) { s = norm(s); return badge(TRC_CLS[s] || 'badge-gray', s.replace(/_/g, ' ') || 'UNKNOWN'); }
  var N_CLS = { SENT: 'badge-blue', PENDING: 'badge-amber', ACKNOWLEDGED: 'badge-green', FAILED: 'badge-red' };
  function notifBadge(s) { s = norm(s); return badge(N_CLS[s] || 'badge-gray', s || 'N/A'); }
  function uploadBadge(s, date) {
    s = norm(s);
    if (s === 'UPLOADED') return badge('badge-green', 'VISTA UPLOAD' + (date ? ' · ' + D(date) : ''));
    if (s === 'NOT_UPLOADED') return badge('badge-red', 'NO VISTA UPLOAD');
    return badge('badge-gray', 'N/A');
  }
  var I_CLS = { PLANNED: 'badge-blue', IN_PROGRESS: 'badge-amber', COMPLETED: 'badge-green', FAILED: 'badge-red' };
  function intBadge(s) { s = norm(s); return badge(I_CLS[s] || 'badge-gray', s.replace(/_/g, ' ') || 'N/A'); }
  function outcomeBadge(s) { s = norm(s); return badge(s === 'PASSED' ? 'badge-green' : s === 'FAILED' ? 'badge-red' : 'badge-gray', s || 'N/A'); }

  /* ───────────── state ───────────── */
  var S = { inChat: false, busy: false, selected: null, replies: [], cfg: { url: '', token_set: false }, seq: 0 };
  var pending = {};

  /* ───────────── transport (Streamlit component or dev server) ───────────── */
  var inStreamlit = false;
  try { inStreamlit = window.parent && window.parent !== window; } catch (e) { inStreamlit = false; }
  function stPost(type, data) { window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data || {}), '*'); }
  function fitFrame() {
    if (!inStreamlit) return;
    var h = 800;
    try { h = window.parent.innerHeight || 800; } catch (e) { /* cross-origin: keep default */ }
    stPost('streamlit:setFrameHeight', { height: h });
  }
  function settle(p) { var w = p && pending[p.nonce]; if (!w) return; delete pending[p.nonce]; clearTimeout(w.t); w.resolve(p); }
  function transport(req) {
    req.nonce = 'n' + Date.now().toString(36) + '-' + (S.seq++);
    return new Promise(function (resolve) {
      var w = { resolve: resolve };
      w.t = setTimeout(function () { settle({ nonce: req.nonce, ok: false, error: 'The agent did not answer within 150 s.' }); }, 150000);
      pending[req.nonce] = w;
      if (inStreamlit) {
        stPost('streamlit:setComponentValue', { value: req, dataType: 'json' });
      } else {
        fetch('api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) })
          .then(function (r) { return r.json(); }).then(settle)
          .catch(function (e) { settle({ nonce: req.nonce, ok: false, error: 'Could not reach the UI server: ' + e }); });
      }
    });
  }
  window.addEventListener('message', function (ev) {
    var d = ev.data || {};
    if (d.type !== 'streamlit:render') return;
    var a = d.args || {};
    if (a.config) { S.cfg = a.config; }
    if (a.payload) { if (a.payload.url) { S.cfg.url = a.payload.url; S.cfg.token_set = !!a.payload.token_set; } settle(a.payload); }
    fitFrame();
  });
  if (inStreamlit) { stPost('streamlit:componentReady', { apiVersion: 1 }); fitFrame(); window.addEventListener('resize', fitFrame); }

  /* ───────────── scrolling / reveal helpers (ported from the mockup) ───────────── */
  function scrollToMsg(el) { var a = $('chat-area'); if (!a || !el) return; var ar = a.getBoundingClientRect(), er = el.getBoundingClientRect(); a.scrollTo({ top: er.top - ar.top + a.scrollTop - 16, behavior: 'smooth' }); }
  function pinToMsg(el) { var a = $('chat-area'); if (!a || !el) return; var ar = a.getBoundingClientRect(), er = el.getBoundingClientRect(); var t = er.top - ar.top + a.scrollTop - 16; if (a.scrollTop < t) a.scrollTo({ top: t, behavior: 'smooth' }); }
  function scrollChat() { var a = $('chat-area'); if (a) a.scrollTop = a.scrollHeight; }
  function resizeWI() { var i = $('welcome-input'); if (!i) return; i.style.height = '0px'; void i.offsetHeight; i.style.height = Math.min(i.scrollHeight, 240) + 'px'; }
  function resizeCI() { var i = $('chat-input'); if (!i) return; i.style.height = '0px'; void i.offsetHeight; i.style.height = Math.min(i.scrollHeight, 200) + 'px'; }

  function animateSubElements(el, pinEl) {
    var groups = [['tr.anim-row', 'row-in', 90], ['.anim-card', 'card-in', 90], ['.anim-item', 'item-in', 90], ['.anim-ehr', 'ehr-in', 60]];
    var delay = 0;
    groups.forEach(function (g) {
      el.querySelectorAll(g[0]).forEach(function (n) {
        (function (e, d) { setTimeout(function () { e.classList.add(g[1]); if (pinEl) pinToMsg(pinEl); }, d); })(n, delay);
        delay += g[2];
      });
    });
  }
  function initReveal(el) {
    el.querySelectorAll('canvas').forEach(function (c) {
      if (c._done || !c.__build) return;
      c._done = true;
      if (window.Chart) { try { c.__chart = c.__build(c); } catch (e) { /* chart failure must not break the answer */ } }
    });
  }
  function revealSeq(arr, i, cb, pinEl, gap) {
    if (i >= arr.length) { if (cb) setTimeout(cb, 250); return; }
    setTimeout(function () {
      arr[i].classList.add('revealed'); initReveal(arr[i]); animateSubElements(arr[i], pinEl);
      if (pinEl) pinToMsg(pinEl); else scrollChat();
      revealSeq(arr, i + 1, cb, pinEl, gap);
    }, i === 0 ? 0 : gap);
  }

  /* ───────────── shell behaviour copied from the mockup (menus, model picker, title menu) ───────────── */
  window.toggleUserMenu = function (e) { e.stopPropagation(); $('user-menu').classList.toggle('open'); var p = $('user-profile'); if (p) p.classList.toggle('active'); };
  document.addEventListener('click', function (e) {
    var menu = $('user-menu');
    if (menu && menu.classList.contains('open') && !e.target.closest('.user-profile-wrap')) { menu.classList.remove('open'); var p = $('user-profile'); if (p) p.classList.remove('active'); }
    if (!e.target.closest('.model-badge') && !e.target.closest('.model-dropdown')) {
      document.querySelectorAll('.model-dropdown.open').forEach(function (x) { x.classList.remove('open'); });
      document.querySelectorAll('.model-badge.active').forEach(function (x) { x.classList.remove('active'); });
    }
    var dd = $('title-dd'); if (dd && dd.classList.contains('open') && !e.target.closest('.chat-title')) dd.classList.remove('open');
  });
  window.toggleModelDropdown = function (e, ddId, badgeId) {
    e.stopPropagation();
    var dd = $(ddId), b = $(badgeId), open = dd.classList.contains('open');
    document.querySelectorAll('.model-dropdown.open').forEach(function (x) { x.classList.remove('open'); });
    document.querySelectorAll('.model-badge.active').forEach(function (x) { x.classList.remove('active'); });
    if (!open) { dd.classList.add('open'); if (b) b.classList.add('active'); }
  };
  window.selectModel = function (opt, name) {
    document.querySelectorAll('.model-option').forEach(function (el) { el.classList.remove('selected'); var t = el.querySelector('.model-option-title'); if (t && t.textContent === name) el.classList.add('selected'); });
    var wl = $('welcome-model-label'), cl = $('chat-model-label'); if (wl) wl.textContent = name; if (cl) cl.textContent = name;
    document.querySelectorAll('.model-dropdown.open').forEach(function (x) { x.classList.remove('open'); });
    document.querySelectorAll('.model-badge.active').forEach(function (x) { x.classList.remove('active'); });
    toast('Model is set on the agent deployment (TRC_AGENT_MODEL_ID); this picker is cosmetic in this build.');
  };
  window.selectEffort = function (btn) { var row = btn.closest('.effort-row'); row.querySelectorAll('.effort-btn').forEach(function (b) { b.classList.remove('selected'); }); btn.classList.add('selected'); };
  window.toggleTitleDD = function () { $('title-dd').classList.toggle('open'); };

  /* ───────────── composer ───────────── */
  function setLock(on) {
    ['welcome', 'chat'].forEach(function (k) {
      var i = $(k + '-input'), b = $(k === 'welcome' ? 'welcome-bar' : 'chat-input-bar'), s = $(k + '-send-btn');
      if (!i) return;
      if (on) { i.setAttribute('readonly', 'readonly'); b.classList.add('disabled'); s.classList.add('disabled'); s.disabled = true; }
      else { i.removeAttribute('readonly'); b.classList.remove('disabled'); refreshSend(k); }
    });
  }
  function refreshSend(k) {
    var i = $(k + '-input'), s = $(k + '-send-btn'); if (!i || !s) return;
    var has = i.value.trim().length > 0 && !S.busy;
    s.classList.toggle('disabled', !has); s.disabled = !has;
  }
  GW.sendFromWelcome = function () { var i = $('welcome-input'); ask(i.value); };
  GW.sendFromChat = function () { var i = $('chat-input'); ask(i.value); };
  function wireComposer() {
    [['welcome', resizeWI], ['chat', resizeCI]].forEach(function (p) {
      var i = $(p[0] + '-input'); if (!i) return;
      i.addEventListener('input', function () { p[1](); refreshSend(p[0]); });
      i.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(i.value); } });
      refreshSend(p[0]);
    });
  }

  /* ───────────── screens ───────────── */
  function fadeWelcome(cb) {
    var ws = $('welcome-screen'), wf = $('welcome-footer'), cs = $('chat-screen');
    ws.classList.add('fading'); wf.classList.add('fading');
    setTimeout(function () {
      ws.classList.add('hidden'); ws.classList.remove('fading'); wf.classList.add('hidden'); wf.classList.remove('fading');
      cs.classList.remove('hidden'); cs.style.display = '';
      if (cb) cb();
    }, 380);
  }
  GW.newChat = function () {
    if (S.busy) { toast('Wait for the current answer to finish.'); return; }
    closeOverlays();
    S.inChat = false; S.selected = null; S.replies = [];
    $('chat-messages').innerHTML = ''; $('typing-indicator').classList.add('hidden');
    ['welcome-input', 'chat-input'].forEach(function (id) { var i = $(id); if (i) { i.value = ''; i.removeAttribute('readonly'); } });
    resizeWI(); resizeCI(); refreshSend('welcome'); refreshSend('chat');
    var ws = $('welcome-screen'), wf = $('welcome-footer');
    ws.classList.remove('hidden', 'fading'); ws.style.cssText = ''; wf.classList.remove('hidden', 'fading'); wf.style.cssText = '';
    $('chat-screen').classList.add('hidden');
    $('chat-title-text').textContent = 'New chat';
    transport({ kind: 'new_chat' });
  };

  /* ───────────── asking the agent ───────────── */
  function addUser(text) {
    var d = document.createElement('div'); d.className = 'msg user'; d.innerHTML = '<div class="msg-bubble">' + E(text) + '</div>';
    $('chat-messages').appendChild(d); scrollToMsg(d);
  }
  function showTyping(label) { $('typing-label').textContent = label || 'Thinking...'; $('typing-indicator').classList.remove('hidden'); scrollToMsg($('typing-indicator')); }
  function hideTyping() { $('typing-indicator').classList.add('hidden'); }

  function ask(text) {
    text = (text || '').trim();
    if (!text || S.busy) return;
    S.busy = true; setLock(true);
    ['welcome-input', 'chat-input'].forEach(function (id) { var i = $(id); if (i) i.value = ''; });
    resizeWI(); resizeCI();
    var go = function () {
      addUser(text); showTyping('Asking the TRC agent...');
      setTimeout(function () { var l = $('typing-label'); if (S.busy && l) l.textContent = 'Calling GuideWell data sources...'; }, 900);
      transport({ kind: 'message', message: text, selected_member_id: S.selected }).then(function (p) { finishTurn(p, text); });
    };
    if (!S.inChat) {
      S.inChat = true;
      $('chat-title-text').textContent = text.length > 44 ? text.slice(0, 42) + '…' : text;
      fadeWelcome(go);
    } else go();
  }
  GW.ask = ask;

  function finishTurn(p, text) {
    hideTyping();
    renderPayload(p, text, function () { S.busy = false; setLock(false); var i = $('chat-input'); if (i) i.focus(); });
  }

  /* ───────────── turning a payload into a message ───────────── */
  function newAssistantShell() {
    var a = document.createElement('div'); a.className = 'msg assistant';
    a.innerHTML = '<div class="msg-bubble" style="max-width:100%;width:100%"><div class="hcc-response trc"></div></div>';
    $('chat-messages').appendChild(a); return a;
  }
  function renderPayload(p, question, done) {
    var a = newAssistantShell(), resp = a.querySelector('.hcc-response');
    if (!p || !p.ok || !p.reply) {
      resp.innerHTML = '<div class="chat-card err"><div class="chat-card-header"><span>The agent could not be reached</span><span class="badge badge-red">Error</span></div><div class="chat-card-body"><p class="prose" style="margin:0">' + E((p && p.error) || 'Unknown error.') + '</p><p class="prose" style="margin:8px 0 0">Nothing was changed. Check the connection in <b>Settings</b> (user menu) and try again.</p></div></div>';
      revealSeq([].slice.call(resp.children), 0, done, a, 200); return;
    }
    var idx = S.replies.length; S.replies.push({ payload: p, question: question });
    a.setAttribute('data-reply', idx);
    var parts = compose(p.reply, p, idx);
    resp.innerHTML = parts.join('');
    wire(resp, p.reply);
    scrollToMsg(a);
    var trace = resp.querySelector('[data-trace]');
    if (trace) runTrace(trace, a, function () { revealRest(resp, a, done); }); else revealRest(resp, a, done);
  }
  function revealRest(resp, a, done) {
    var arr = [].filter.call(resp.children, function (k) { return !k.hasAttribute('data-trace'); });
    revealSeq(arr, 0, done, resp.querySelector('[data-trace]') ? a : null, 260);
  }
  function runTrace(el, a, cb) {
    el.classList.add('revealed', 'expanded', 'active');
    var hdr = el.querySelector('[data-role="trace-header"]');
    hdr.addEventListener('click', function (e) { e.stopPropagation(); if (el.classList.contains('active')) return; el.classList.toggle('expanded'); });
    var steps = el.querySelectorAll('.ehr-step'), meta = el.querySelector('[data-meta]'), per = Math.max(60, Math.min(160, 1200 / Math.max(steps.length, 1)));
    steps.forEach(function (s, i) { setTimeout(function () { s.classList.add('visible'); pinToMsg(a); }, i * per + 80); });
    setTimeout(function () { meta.textContent = '· ' + steps.length + ' steps completed · ' + (el.getAttribute('data-ms') || '?') + ' ms'; el.classList.remove('active', 'expanded'); setTimeout(cb, 250); }, steps.length * per + 260);
  }

  /* delegated actions: no inline handlers inside answers */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-act]'); if (!t) return;
    var act = t.getAttribute('data-act'), root = t.closest('.hcc-response');
    if (act === 'ask') { ask(t.getAttribute('data-q')); }
    else if (act === 'open-member') { S.selected = t.getAttribute('data-id'); ask('Open the TRC record for ' + S.selected); }
    else if (act === 'scroll') { var tg = root && root.querySelector(t.getAttribute('data-sel')); var ar = $('chat-area'); if (tg && ar) { var r1 = ar.getBoundingClientRect(), r2 = tg.getBoundingClientRect(); ar.scrollTo({ top: r2.top - r1.top + ar.scrollTop - 16, behavior: 'smooth' }); } }
    else if (act === 'sub') { var w = t.closest('.rec-root'); w.querySelectorAll('.subview').forEach(function (v) { v.classList.remove('active'); }); w.querySelectorAll('.subtab-btn').forEach(function (b) { b.classList.remove('active'); }); var v = w.querySelector('.subview[data-sub="' + t.getAttribute('data-sub') + '"]'); if (v) v.classList.add('active'); t.classList.add('active'); }
    else if (act === 'view') { var wl = t.closest('.wl-root'); var m = t.getAttribute('data-mode'); wl.querySelector('.member-grid').style.display = m === 'card' ? 'grid' : 'none'; wl.querySelector('.wl-table').style.display = m === 'table' ? 'block' : 'none'; wl.querySelectorAll('.view-toggle button').forEach(function (b) { b.classList.toggle('active', b === t); }); }
    else if (act === 'raw') { var box = t.nextElementSibling; box.classList.toggle('show'); t.textContent = box.classList.contains('show') ? '▾ hide raw HL7 v2.5 segment' : '▸ view raw HL7 v2.5 segment'; }
    else if (act === 'confirm') { confirmAction(t); }
    else if (act === 'log-form') { var f = t.parentNode.querySelector('.inline-form'); if (f) { f.style.display = f.style.display === 'flex' ? 'none' : 'flex'; var inp = f.querySelector('input'); if (inp) inp.focus(); } }
    else if (act === 'log-send') { var f2 = t.closest('.inline-form'), v2 = f2.querySelector('input').value.trim(); if (v2) ask('Log an intervention for ' + t.getAttribute('data-id') + ': ' + v2); }
    else if (act === 'apply-dash') { var sel = root.querySelector('select[data-f="facility"]'); var fv = sel && sel.value; ask(fv && fv.indexOf('All Facilities') !== 0 ? 'Show the worklist for ' + fv : 'How are we doing on TRC? Show the dashboard.'); }
    else if (act === 'flow') { GW.openFlow(parseInt(t.getAttribute('data-idx'), 10)); }
    else if (act === 'toggle-trace') { /* handled in runTrace */ }
  });
  document.addEventListener('input', function (e) { var r = e.target.closest('[data-filter-root]'); if (r) applyFilters(r.closest('.hcc-response')); });
  document.addEventListener('change', function (e) { var r = e.target.closest('[data-filter-root]'); if (r) applyFilters(r.closest('.hcc-response')); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.closest && e.target.closest('.inline-form')) { var b = e.target.closest('.inline-form').querySelector('button'); if (b) b.click(); }
    if (e.key === 'Escape') closeOverlays();
  });

  /* confirmation (Approve / Reject) — the ticket is signed by the agent; the page only relays it */
  function confirmAction(btn) {
    if (S.busy) return;
    var card = btn.closest('.chat-card'), ticket = btn.getAttribute('data-ticket'), decision = btn.getAttribute('data-decision');
    card.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    S.busy = true; setLock(true); showTyping(decision === 'approve' ? 'Sending the approved action...' : 'Cancelling...');
    transport({ kind: 'confirm', ticket: ticket, decision: decision, selected_member_id: S.selected }).then(function (p) {
      hideTyping();
      var note = card.querySelector('.confirm-note');
      if (note) note.textContent = decision === 'approve' ? 'Approved — result below.' : 'Rejected — nothing was changed.';
      card.querySelector('.chat-card-header .badge').outerHTML = decision === 'approve' ? '<span class="badge badge-green">Approved</span>' : '<span class="badge badge-gray">Rejected</span>';
      renderPayload(p, (decision === 'approve' ? 'Approve: ' : 'Reject: ') + (btn.getAttribute('data-summary') || ''), function () { S.busy = false; setLock(false); });
    });
  }

  /* client-side filters over rows already returned by a tool (no data is invented; this only hides rows) */
  function applyFilters(resp) {
    if (!resp) return;
    var root = resp.querySelector('[data-filter-root]'); if (!root) return;
    var q = (root.querySelector('[data-f="search"]') || {}).value || '';
    var fs = {}; root.querySelectorAll('select[data-f]').forEach(function (s) { fs[s.getAttribute('data-f')] = s.value; });
    var shown = 0, total = 0;
    resp.querySelectorAll('[data-row]').forEach(function (r) {
      var d = JSON.parse(r.getAttribute('data-row')), ok = true;
      if (q && (d.name + ' ' + d.id + ' ' + (d.mrn || '') + ' ' + (d.facility || '')).toLowerCase().indexOf(q.toLowerCase()) < 0) ok = false;
      Object.keys(fs).forEach(function (k) { var v = fs[k]; if (!v || /^All/.test(v)) return; if (norm(d[k]) !== norm(v.replace(/ \(.*\)$/, '').replace(/^NOT UPLOADED.*/, 'NOT_UPLOADED'))) ok = false; });
      r.style.display = ok ? '' : 'none';
      var primary = resp.querySelector('.member-card') ? r.classList.contains('member-card') : r.tagName === 'TR';
      if (primary && r.hasAttribute('data-count')) { total++; if (ok) shown++; }
    });
    var c = resp.querySelector('[data-shown]'); if (c) c.textContent = shown;
  }
  function wire(resp, reply) {
    /* charts get their builders attached by compose() through data-chart ids; nothing else to wire here */
    resp.querySelectorAll('canvas[data-chart]').forEach(function (c) { var f = CHARTS[c.getAttribute('data-chart')]; if (f) c.__build = f; });
  }
  var CHARTS = {};

  /* __PART2__ */

  /* ───────────── boot ───────────── */
  GW._S = S; GW._compose = function (r, p) { return compose(r, p, 0); };
  var booted = false;
  function boot() {
    if (booted) return; booted = true;
    wireComposer(); buildWelcomeRecs();
    if (!inStreamlit) { fetch('api/config').then(function (r) { return r.json(); }).then(function (c) { S.cfg = c; }).catch(function () { }); }
  }
  document.addEventListener('DOMContentLoaded', boot);
  if (document.readyState !== 'loading') boot();
})();
