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

    /* ───────────── trace: the mockup's "Connecting to GuideWell data sources" card, filled from the REAL tool_trace ───────────── */
  var TOOL_BLURB = {
    get_trc_summary: 'discharge funnel, closure rate and risk tiers', get_trc_metric_breakdown: 'compliance by component / facility / disposition / trend',
    get_trc_worklist: 'TRC worklist ranked by risk', get_closure_board: 'TRC closure board', get_validation_summary: 'validation agent summary',
    list_provider_outreach: 'provider notification tracking', get_provider_outreach: 'notification, response and Vista upload for one member',
    get_member_details: 'demographics, admission and discharge', get_member_trc_status: 'TRC measure status', get_validation_evidence: 'upload, claim and Care Navi evidence',
    get_member_adt_timeline: 'ADT event history (HL7 v2.5)', get_discharge_summary: 'discharge summary', get_discharge_medications: 'discharge medications',
    get_followup_status: 'PCP follow-up timeframe', get_risk_assessment: 'readmission risk score', get_intervention_status: 'Care Navi intervention',
    get_prior_admissions: 'prior admissions', get_attachments: 'provider uploads, discharge summaries and CCDAs (read-only)', get_provider_contacts: 'verified provider contacts',
    get_member_audit_trail: 'audit trail', get_mrat_review_status: 'MRAT review status', get_attachment_access_link: 'short-lived read-only access link',
    validate_claims: 'deterministic claims match within the 3-day window', load_member_trc_record: 'full member record (parallel reads)',
    run_validation_and_load_closure_board: 'validation run, then closure board',
    send_provider_notification: 'resend provider alert', resend_notifications_bulk: 'bulk resend provider alerts', escalate_to_provider_manager: 'escalate to provider manager',
    log_intervention_activity: 'log intervention activity', update_review_status: 'soft-close and route to MRAT', request_worklist_export: 'worklist export'
  };
  function traceTitle(reply) {
    var i = String(reply.intent || '');
    if (/^MEMBER_TRC_RECORD|^MEMBER_/.test(i)) return 'Retrieving member record';
    if (/MEDICAL_RECORDS|ATTACH/.test(i)) return 'Connecting to Provider Vista, EIP and Content Central';
    if (/^ACTION_/.test(i) || /\+ACTION_/.test(i)) return 'Preparing the requested action';
    return 'Connecting to GuideWell data sources';
  }
  function traceHtml(reply, p) {
    var tr = reply.tool_trace || [], onprem = ((p.demo || {}).onprem_calls || []), steps = [];
    function step(cls, icon, body, time) { return '<div class="ehr-step ' + cls + '"><span class="es-icon">' + icon + '</span><span class="es-body">' + body + '</span><span class="es-time">' + time + '</span></div>'; }
    steps.push(step('', CHECK, 'Request authenticated and sent to the <b>GWChat Integration Agent</b> (AgentCore Runtime)', ''));
    steps.push(step('', CHECK, 'Agent chose <b>' + tr.length + '</b> allow-listed tool' + (tr.length === 1 ? '' : 's') + ' · intent <b>' + E(reply.intent) + '</b>', ''));
    tr.forEach(function (t) {
      var held = t.outcome === 'queued_for_confirmation', blocked = t.outcome === 'blocked';
      var routes = onprem.filter(function (o) { return o.tool === t.tool; }).map(function (o) { return E(o.method + ' ' + o.route); });
      var body = 'MCP <b>' + E(t.tool) + '()</b> — ' + E(TOOL_BLURB[t.tool] || 'tool call') +
        (held ? ' · <b>write held for your approval</b>' : blocked ? ' · <b>blocked</b> (' + E(t.error_code) + ')' : !t.ok ? ' · <b>failed</b> (' + E(t.error_code) + ')' : '') +
        (routes.length ? '<span class="es-sub">on-prem ' + routes.slice(0, 2).join(', ') + '</span>' : '');
      steps.push(step(held ? 'hold' : (blocked || !t.ok) ? 'fail' : '', held ? HOLD : (blocked || !t.ok) ? CROSS : CHECK, body, t.latency_ms !== null && t.latency_ms !== undefined ? t.latency_ms + ' ms' : ''));
    });
    steps.push(step('', CHECK, 'Answer assembled from tool results only — <b>' + (reply.blocks || []).length + '</b> block' + ((reply.blocks || []).length === 1 ? '' : 's') + ', <b>' + (reply.data_gaps || []).length + '</b> data gap' + ((reply.data_gaps || []).length === 1 ? '' : 's'), (p.http_ms || '?') + ' ms'));
    return '<div class="ehr-trace" data-trace="ehr" data-ms="' + (p.http_ms || '') + '"><div class="ehr-trace-header" data-role="trace-header"><span class="et-icon">' + DB + '</span><span class="et-title">' + E(traceTitle(reply)) + '</span><span class="et-meta" data-meta="1">· Connecting...</span><span class="et-chevron">' + CHEV + '</span></div><div class="ehr-trace-body">' + steps.join('') + '</div></div>';
  }

  /* ───────────── compose: one agent reply → mockup components ───────────── */
  function group(blocks) {
    var g = {}; (blocks || []).forEach(function (b) { (g[b.type] = g[b.type] || []).push(b); }); return g;
  }
  function gapsCard(gaps) {
    if (!gaps || !gaps.length) return '';
    return '<div class="chat-card warn"><div class="chat-card-header"><span>Some data is unavailable</span><span class="badge badge-amber">' + gaps.length + ' gap' + (gaps.length === 1 ? '' : 's') + '</span></div><div class="chat-card-body"><ul class="gap-list">' +
      gaps.map(function (g) { return '<li><b>' + E(g.section || g.tool) + '</b> — ' + E(g.message || g.code) + ' <span style="color:var(--trc-muted)">(' + E(g.code) + (g.retryable ? ', retryable' : '') + ')</span></li>'; }).join('') +
      '</ul><div class="confirm-note" style="margin-top:8px">These values were not looked up from anywhere else and have not been inferred.</div></div></div>';
  }
  function confirmCard(pa) {
    var args = pa.arguments || {}, keys = Object.keys(args);
    var rows = keys.map(function (k) { var v = args[k]; return [T(k), Array.isArray(v) ? v.map(E).join(', ') : E(v)]; });
    return '<div class="chat-card warn"><div class="chat-card-header"><span>Approval required — ' + E(pa.tool) + '</span><span class="badge badge-amber">Awaiting you</span></div><div class="chat-card-body">' +
      '<p class="prose" style="margin:0 0 8px"><b>' + E(pa.summary) + '</b></p>' + (rows.length ? kv(rows) : '') +
      '<div class="confirm-actions"><button class="btn btn-primary" data-act="confirm" data-decision="approve" data-ticket="' + Aq(pa.ticket) + '" data-summary="' + Aq(pa.summary) + '">Approve</button>' +
      '<button class="btn" data-act="confirm" data-decision="reject" data-ticket="' + Aq(pa.ticket) + '" data-summary="' + Aq(pa.summary) + '">Reject</button>' +
      '<span class="confirm-note">Nothing is changed until you approve. Expires ' + E(DT(pa.expires_at)) + ' UTC.</span></div></div></div>';
  }
  function actionResultCard(b) {
    var d = b.data || {}, rows = Object.keys(d).map(function (k) { var v = d[k]; return [T(k), typeof v === 'boolean' ? (v ? 'Yes' : 'No') : Array.isArray(v) ? v.map(E).join(', ') : typeof v === 'object' && v ? E(JSON.stringify(v)) : E(nz(v))]; });
    return '<div class="chat-card ok"><div class="chat-card-header"><span>' + E(b.title || 'Action result') + '</span><span class="badge badge-green">Done</span></div><div class="chat-card-body">' + kv(rows) + '<div class="lock-note">🔒 Final MRAT closure remains a human (HEDIS nurse) step.</div></div></div>';
  }

  /* dashboard pieces ------------------------------------------------------------------------------------------------------------------------- */
  var PAL = { teal: '#1bb3ba', amber: '#d9992b', red: '#e0504f', green: '#2b9e63', blue: '#3b7dd8', muted: '#8a9a9c', purple: '#8f6fd1', pink: '#c98fd1' };
  var cid = 0;
  function chartBox(kind, builder, short) { var id = 'ch' + (cid++); CHARTS[id] = builder; return '<div class="chart-box' + (short ? ' short' : '') + '"><canvas data-chart="' + id + '"></canvas></div>'; }
  function fmtPoint(pt) { return pt.unit === 'percent' ? pct(pt.value) : num(pt.value); }
  function breakdownPanel(b, summary) {
    var d = b.data, pts = d.points || [], dim = d.dimension, ids = '';
    if (!pts.length) return panel('TRC breakdown', '', '<div class="empty">No points returned.</div>');
    if (dim === 'COMPONENT') {
      return panel('TRC Measure Components — Compliance', '', '<table><tr><th>Component</th><th>Discharges</th><th>Compliant</th></tr>' + pts.map(function (r) {
        return '<tr class="anim-row"><td>' + E(r.label) + '</td><td>' + num(r.denominator) + '</td><td><span class="rate-bar-wrap"><span class="rate-bar" style="width:' + Math.min(100, r.value) + '%;"></span></span>' + fmtPoint(r) + '</td></tr>'; }).join('') + '</table>');
    }
    if (dim === 'FACILITY') {
      return panel('Top Facilities by Open TRC Gaps', '', '<table><tr><th>Facility</th><th>Discharges</th><th>Open Gap</th></tr>' + pts.map(function (r) {
        return '<tr class="anim-row"><td>' + E(r.label) + '</td><td>' + num(r.denominator) + '</td><td><span class="rate-bar-wrap"><span class="rate-bar" style="width:' + Math.min(100, r.value * 1.6) + '%;"></span></span>' + fmtPoint(r) + '</td></tr>'; }).join('') + '</table>');
    }
    if (dim === 'DISPOSITION') {
      var cols = [PAL.teal, PAL.blue, PAL.amber, PAL.purple, PAL.red, PAL.pink, PAL.muted];
      return panel('Discharge Disposition Breakdown', E(d.measurement_period), chartBox('doughnut', function (c) {
        return new Chart(c, { type: 'doughnut', data: { labels: pts.map(function (x) { return x.label; }), datasets: [{ data: pts.map(function (x) { return x.value; }), backgroundColor: pts.map(function (_, i) { return cols[i % cols.length]; }) }] },
          options: { plugins: { legend: { position: 'right', labels: { boxWidth: 10, font: { size: 10.5 } } } }, maintainAspectRatio: false, cutout: '62%' } });
      }));
    }
    if (dim === 'TREND') {
      var target = summary && summary.plan_target_pct;
      return panel('TRC Gap Closure Rate — Trailing 12 Months', target ? 'Dashed line = ' + pct(target) + ' plan target' : '', chartBox('line', function (c) {
        var ds = [{ label: 'TRC Gap Closure Rate', data: pts.map(function (x) { return x.value; }), borderColor: PAL.teal, backgroundColor: 'rgba(27,179,186,.12)', tension: .35, fill: true, pointRadius: 3 }];
        if (target) ds.push({ label: 'Plan Target', data: pts.map(function () { return target; }), borderColor: PAL.red, borderDash: [6, 4], pointRadius: 0, fill: false });
        return new Chart(c, { type: 'line', data: { labels: pts.map(function (x) { return x.label; }), datasets: ds },
          options: { plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 10.5 } } } }, scales: { y: { ticks: { callback: function (v) { return v + '%'; } }, grid: { color: '#eef2f2' } }, x: { grid: { display: false } } }, maintainAspectRatio: false } });
      }));
    }
    return panel('TRC breakdown — ' + T(dim), E(d.measurement_period), '<table><tr><th>Label</th><th>Value</th></tr>' + pts.map(function (r) { return '<tr><td>' + E(r.label) + '</td><td>' + fmtPoint(r) + '</td></tr>'; }).join('') + '</table>');
  }
  function priorityList(items) {
    return '<div class="chat-card"><div class="chat-card-body">' + items.map(function (m) {
      return '<div class="doc-item anim-item" style="cursor:pointer;" data-act="open-member" data-id="' + Aq(m.member_id) + '"><div><div class="di-name">' + E(m.member_name) + ' · ' + E(m.member_id) + '</div><div class="di-sub">' + E(m.diagnosis) + ' · Discharged ' + D(m.discharge_date) + ' · ' + E(m.facility) + ' · PCP follow-up due ' + D(m.followup_due) + '</div></div><div>' + riskBadge(m.risk_tier) + ' ' + uploadBadge(m.provider_upload_status) + '</div></div>'; }).join('') + '</div></div>';
  }
  function dashboard(G, reply) {
    var out = [], b = G.KPI_SUMMARY[0], s = b.data;
    var asOf = new Date(b.as_of), mon = isNaN(asOf) ? '' : asOf.toLocaleString('en-US', { month: 'short', year: 'numeric' });
    var onTarget = s.plan_target_pct !== null && s.plan_target_pct !== undefined && s.closure_rate_pct >= s.plan_target_pct;
    out.push('<div class="chat-card"><div class="chat-card-header"><span>TRC Snapshot' + (mon ? ' — ' + E(mon) : '') + '</span>' + badge(onTarget ? 'badge-green' : 'badge-amber', onTarget ? 'On target' : 'Watch') + '</div><div class="chat-card-body"><div class="mini-kpis">' +
      mk(num(s.discharges_identified), 'Discharges Identified') + mk(pct(s.provider_notified.rate), 'Provider Notified') + mk(num(s.no_upload_by_day3), 'No Upload by Day 3') + mk(pct(s.closure_rate_pct), 'Soft Closed') +
      '</div><button class="open-dash-btn" data-act="scroll" data-sel=".filterbar">Open Full Dashboard →</button></div></div>');
    function mk(n, l) { return '<div class="mini-kpi anim-card"><div class="num">' + n + '</div><div class="lbl">' + l + '</div></div>'; }
    var fac = (G.METRIC_BREAKDOWN || []).filter(function (x) { return x.data.dimension === 'FACILITY'; })[0];
    var per = String(s.measurement_period || '').split('/');
    out.push('<div class="filterbar"><div class="filter-item"><label>Discharge Date Range</label><input type="text" class="select-inline" value="' + Aq(per.length === 2 ? D(per[0]) + ' – ' + D(per[1]) : '') + '" readonly></div>' +
      '<div class="filter-item"><label>Facility</label><select class="select-inline" data-f="facility"><option>All Facilities' + (fac ? ' (' + fac.data.points.length + ')' : '') + '</option>' + (fac ? fac.data.points.map(function (p) { return '<option>' + E(p.label) + '</option>'; }).join('') : '') + '</select></div>' +
      '<div class="filter-item"><label>Line of Business</label><select class="select-inline" disabled title="The current tools do not filter the dashboard by line of business"><option>All</option></select></div>' +
      '<div class="filter-spacer"></div><button class="btn" data-act="ask" data-q="Export the TRC worklist as CSV">Export CSV</button><button class="btn" data-act="ask" data-q="Export the TRC worklist as PDF">Export PDF</button><button class="btn btn-primary" data-act="apply-dash">Apply Filters</button></div>');
    function rate(r, good) { return badge(r === null || r === undefined ? 'badge-gray' : r >= good ? 'badge-green' : 'badge-amber', pct(r)); }
    out.push('<div class="kpi-row">' +
      kc('① Discharge Identified', num(s.discharges_identified), 'ADT A03 inpatient discharges · TRC Proxy Task opened', '') +
      kc('② Provider Notified', num(s.provider_notified.count) + ' ' + rate(s.provider_notified.rate, 90), 'Standardized alert via Email / Fax / Provider Proxy Task', '') +
      kc('③ Validation Passed', num(s.validation_passed.count) + ' ' + rate(s.validation_passed.rate, 70), 'Records uploaded + claim matched in the 3-day window', '') +
      kc('④ Soft Closed', num(s.soft_closed.count) + ' ' + rate(s.soft_closed.rate, s.plan_target_pct || 60), num(s.mrat_final_closed) + ' final-closed in MRAT by HEDIS nurse', onTarget ? 'flag-green' : '') + '</div>');
    function kc(l, v, sub, cls) { return '<div class="kpi-card anim-card"><div class="lbl">' + l + '</div><div class="val ' + cls + '">' + v + '</div><div class="sub">' + sub + '</div></div>'; }
    var by = {}; (G.METRIC_BREAKDOWN || []).forEach(function (x) { by[x.data.dimension] = x; });
    var row1 = [by.TREND, by.DISPOSITION].filter(Boolean).map(function (x) { return breakdownPanel(x, s); });
    if (row1.length) out.push('<div class="two-col">' + row1.join('') + '</div>');
    var row2 = [by.COMPONENT, by.FACILITY].filter(Boolean).map(function (x) { return breakdownPanel(x, s); });
    if (row2.length) out.push('<div class="two-col">' + row2.join('') + '</div>');
    Object.keys(by).forEach(function (k) { if (['TREND', 'DISPOSITION', 'COMPONENT', 'FACILITY'].indexOf(k) < 0) out.push(breakdownPanel(by[k], s)); });
    var tiers = s.risk_tiers || [];
    out.push('<div class="panel"><h3>Risk Tier Distribution</h3><div class="panel-sub">' + num(s.active_window_members) + ' members in an active TRC window (last 30 days) · segmented by AI risk score</div><div class="kpi-row" style="margin-bottom:0;">' +
      tiers.map(function (t) { var tn = norm(t.tier); return '<div class="kpi-card anim-card"><div class="lbl">' + (tn === 'HIGH' ? 'HIGH RISK (&gt;20%)' : tn === 'MEDIUM' ? 'MEDIUM RISK (10–20%)' : tn === 'LOW' ? 'LOW RISK (&lt;10%)' : E(t.tier)) + '</div><div class="val ' + (tn === 'HIGH' ? 'flag-red' : tn === 'LOW' ? 'flag-green' : '') + '"' + (tn === 'MEDIUM' ? ' style="color:var(--amber);"' : '') + '>' + num(t.count) + '</div><div class="sub">' + E(t.note || '') + '</div></div>'; }).join('') +
      '<div class="kpi-card anim-card"><div class="lbl">Awaiting MRAT Closure</div><div class="val">' + num(s.awaiting_mrat_closure) + '</div><div class="sub">Soft closed · pending HEDIS nurse validation</div></div></div></div>');
    if (G.WORKLIST) {
      var items = G.WORKLIST[0].data.items || [];
      if (items.length) { out.push('<p class="prose">Highest-priority members from <b>get_trc_worklist()</b> — HIGH risk, past day 3 with no Provider Vista upload (' + items.length + ' of ' + num(G.WORKLIST[0].data.total_matching) + '). Select one to open the TRC record:</p>'); out.push(priorityList(items)); }
      else out.push('<p class="prose">No HIGH-risk members past day 3 without an upload were returned.</p>');
    }
    return out;
  }

  /* worklist ------------------------------------------------------------------------------------------------------------------------------- */
  function rowData(m) { return Aq(JSON.stringify({ name: m.member_name, id: m.member_id, facility: m.facility, eligibility: m.eligibility, disposition: m.disposition, trc_status: m.trc_status, provider_upload_status: m.provider_upload_status, risk_tier: m.risk_tier })); }
  function worklistFull(b) {
    var d = b.data, items = d.items || [];
    if (!items.length) return ['<div class="panel"><h3>TRC worklist</h3><div class="empty">No members matched the filters.</div></div>'];
    var dispos = ['HOME', 'HOME_WITH_SERVICES', 'TRANSFERRED_TO_SNF', 'TRANSFERRED_TO_REHAB'];
    items.forEach(function (m) { if (m.disposition && dispos.indexOf(m.disposition) < 0) dispos.push(m.disposition); });
    var f = '<div class="filterbar" data-filter-root="1">' +
      fi('Search', '<input type="text" class="select-inline" data-f="search" placeholder="Member name, HCCID, or facility" style="width:200px;">') +
      fi('Eligibility', sel('eligibility', ['All', 'ELIGIBLE', 'INELIGIBLE'])) + fi('Disposition', sel('disposition', ['All'].concat(dispos))) +
      fi('TRC Status', sel('trc_status', ['All', 'DISCHARGE IDENTIFIED', 'PROVIDER NOTIFIED', 'VALIDATION PASSED', 'SOFT CLOSED', 'MRAT CLOSED'])) +
      fi('Provider Upload', sel('provider_upload_status', ['All', 'UPLOADED', 'NOT UPLOADED (past day 3)'])) + fi('Risk Tier', sel('risk_tier', ['All', 'HIGH', 'MEDIUM', 'LOW'])) +
      '<div class="filter-spacer"></div><div class="view-toggle"><button class="active" data-act="view" data-mode="card">▦ Cards</button><button data-act="view" data-mode="table">☰ Table</button></div></div>';
    function fi(l, h) { return '<div class="filter-item"><label>' + l + '</label>' + h + '</div>'; }
    function sel(k, opts) { return '<select class="select-inline" data-f="' + k + '">' + opts.map(function (o) { return '<option>' + E(o.replace(/_/g, ' ')) + '</option>'; }).join('') + '</select>'; }
    var sorted = items.slice();
    var cards = sorted.map(function (m) {
      return '<div class="member-card anim-card risk-' + norm(m.risk_tier).toLowerCase() + '" data-row="' + rowData(m) + '" data-count="1" data-act="open-member" data-id="' + Aq(m.member_id) + '"><div class="mc-top"><div><div class="mc-name">' + E(m.member_name) + '</div><div class="mc-id">' + E(m.member_id) + ' · ' + T(nz(m.line_of_business)) + '</div></div>' + riskBadge(m.risk_tier) + '</div>' +
        row('Admit → Discharge', D(m.admit_date) + ' → ' + D(m.discharge_date)) + row('Facility', E(m.facility)) + row('Diagnosis', E(first(m.diagnosis))) + row('Disposition', T(m.disposition)) + row('PCP Follow-up Due', D(m.followup_due)) +
        '<div class="mc-badges">' + trcBadge(m.trc_status) + notifBadge(m.notification_status) + uploadBadge(m.provider_upload_status) + (norm(m.eligibility) === 'INELIGIBLE' ? badge('badge-gray', 'INELIGIBLE') : '') + '</div></div>';
    }).join('');
    function row(k, v) { return '<div class="mc-row"><span class="k">' + k + '</span><span>' + v + '</span></div>'; }
    var trs = sorted.map(function (m) {
      return '<tr class="anim-row" data-row="' + rowData(m) + '" data-count="1"><td class="link-row" data-act="open-member" data-id="' + Aq(m.member_id) + '">' + E(m.member_name) + '</td><td>' + E(m.member_id) + '</td><td>' + D(m.admit_date) + ' → ' + D(m.discharge_date) + '</td><td>' + E(m.facility) + '</td><td>' + E(first(m.diagnosis)) + '</td><td>' + T(m.disposition) + '</td><td>' + trcBadge(m.trc_status) + '</td><td>' + riskBadge(m.risk_tier) + '</td><td>' + notifBadge(m.notification_status) + '</td><td>' + uploadBadge(m.provider_upload_status) + '</td><td>' + D(m.followup_due) + '</td></tr>';
    }).join('');
    var af = d.applied_filters || {}, fl = Object.keys(af).filter(function (k) { return af[k] !== null && af[k] !== false && k !== 'limit'; }).map(function (k) { return T(k) + (af[k] === true ? '' : ' = ' + E(af[k])); });
    return ['<div class="wl-root">' + f + '<div style="font-size:12.5px;color:var(--muted);margin-bottom:10px;">Showing <b data-shown="1">' + items.length + '</b> of ' + num(d.total_matching) + ' TRC discharges · sorted by ' + T(d.sort || 'risk_score_desc').toLowerCase() + (fl.length ? ' · tool filters: ' + fl.join(', ') : '') + (d.next_cursor ? ' · more rows exist (cursor returned)' : '') + '</div>' +
      '<div class="member-grid">' + cards + '</div><div class="panel wl-table" style="display:none;"><table><tr><th>Member</th><th>HCCID</th><th>Admit → Discharge</th><th>Facility</th><th>Diagnosis</th><th>Disposition</th><th>TRC Status</th><th>Risk</th><th>Notification</th><th>Provider Upload</th><th>Follow-up Due</th></tr>' + trs + '</table></div></div>'];
  }

  /* notifications -------------------------------------------------------------------------------------------------------------------------- */
  function notifications(b) {
    var d = b.data, items = d.items || [];
    var facs = [], chans = [];
    items.forEach(function (i) { if (i.facility && facs.indexOf(i.facility) < 0) facs.push(i.facility); if (i.channel && chans.indexOf(i.channel) < 0) chans.push(i.channel); });
    var f = '<div class="filterbar" data-filter-root="1"><div class="filter-item"><label>Status</label><select class="select-inline" data-f="status"><option>All</option><option>SENT</option><option>PENDING</option><option>ACKNOWLEDGED</option><option>FAILED</option></select></div>' +
      '<div class="filter-item"><label>Channel</label><select class="select-inline" data-f="channel"><option>All</option>' + chans.map(function (c) { return '<option>' + E(c) + '</option>'; }).join('') + '</select></div>' +
      '<div class="filter-item"><label>Facility</label><select class="select-inline" data-f="facility"><option>All Facilities</option>' + facs.map(function (c) { return '<option>' + E(c) + '</option>'; }).join('') + '</select></div>' +
      '<div class="filter-spacer"></div><button class="btn" data-act="ask" data-q="Bulk resend to non-responsive providers">Bulk Resend to Non-Responsive</button></div>';
    var rows = items.map(function (i) {
      var rd = Aq(JSON.stringify({ name: i.member_name, id: i.member_id, facility: i.facility, status: i.status, channel: i.channel }));
      return '<tr class="anim-row" data-row="' + rd + '" data-count="1"><td><span class="link-row" data-act="open-member" data-id="' + Aq(i.member_id) + '">' + E(i.member_name) + '</span> <span style="color:var(--trc-muted);font-size:11px;">' + E(i.member_id) + '</span></td><td>' + E(i.event) + '</td><td>' + E(i.provider_name) + '</td><td>' + T(i.channel) + '</td><td>' + DT(i.sent_at) + '</td><td>' + notifBadge(i.status) + '</td><td>' + badge('badge-blue', String(i.provider_response || '').replace(/_/g, ' ')) + '</td><td>' + uploadBadge(i.vista_upload) + '</td><td>' +
        (i.resend_allowed ? '<button class="btn" data-act="ask" data-q="Resend the provider alert for ' + Aq(i.member_id) + '">Resend</button>' : '<span style="color:var(--trc-muted);font-size:11.5px;">—</span>') + '</td></tr>';
    }).join('');
    return ['<div class="wl-root">' + f + '<div class="panel"><h3>TRC Provider Notification Tracking</h3><div class="panel-sub">Admission (A01) &amp; discharge (A03) alerts · Outbound via Email, Fax or Provider Proxy Task · showing <b data-shown="1">' + items.length + '</b> of ' + num(d.total_matching) + '</div>' +
      (items.length ? '<table><tr><th>Member</th><th>Event</th><th>Provider</th><th>Channel</th><th>Sent</th><th>Status</th><th>Provider Response</th><th>Vista Upload</th><th>Action</th></tr>' + rows + '</table>' : '<div class="empty">No notifications matched.</div>') + '</div></div>'];
  }

  /* member record (all tabs) -------------------------------------------------------------------------------------------------------------- */
  function memberRecord(b, gaps) {
    var d = b.data, U = function (k) { return unavailable(k, gaps); };
    var tabs = [['trc', 'TRC Measure Status'], ['timeline', 'ADT Timeline'], ['discharge', 'Discharge Summary'], ['risk', 'Risk & Follow-up'], ['notif', 'Provider Notification'], ['compare', 'Prior Admissions'], ['records', 'Medical Records']];
    var mid = d.details ? d.details.member_id : (d.trc_status && d.trc_status.member_id);
    var out = '<span class="back-link" data-act="ask" data-q="Show members discharged in the last 14 days where the provider has not uploaded documents by day 3, ranked by risk">← Back to Members</span>';
    out += d.details ? detailHeader(d.details, d.risk) : '<div class="panel">' + U('get_member_details') + '</div>';
    out += '<div class="subtabs">' + tabs.map(function (t, i) { return '<button class="subtab-btn' + (i ? '' : ' active') + '" data-act="sub" data-sub="' + t[0] + '">' + t[1] + '</button>'; }).join('') + '</div>';
    function sv(k, inner, first) { return '<div class="subview' + (first ? ' active' : '') + '" data-sub="' + k + '">' + inner + '</div>'; }
    var ev = secEvidence(d.validation_evidence);
    out += sv('trc', '<div class="two-col"><div class="panel"><h3>Measure Status</h3><div class="panel-sub">Deterministic Validation Agent · rule-based checks</div>' + (secStatus(d.trc_status) || U('get_member_trc_status')) + '</div>' +
      '<div class="panel"><h3>Attachments &amp; Evidence</h3><div class="panel-sub">Sourced via get_validation_evidence()</div>' + (ev || U('get_validation_evidence')) +
      '<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;"><button class="btn btn-primary" data-act="ask" data-q="Show the MRAT status for ' + Aq(mid) + '">View Details / MRAT Closure</button><button class="btn" data-act="ask" data-q="Run the validation agent and show the closure board">Re-run validate_claims()</button></div>' +
      lockNote('The HEDIS nurse completes final closure in MRAT (human-in-the-loop). update_review_status() syncs the status back to GWChat.') + '</div></div>', true);
    out += sv('timeline', '<div class="panel"><h3>Full Admission Timeline — ADT Event History (HL7 v2.5)</h3><div class="panel-sub">' + E((d.adt_timeline && d.adt_timeline.source) || 'ADT / HIE') + '</div>' + (secTimeline(d.adt_timeline) || U('get_member_adt_timeline')) + '</div>');
    out += sv('discharge', '<div class="two-col"><div class="panel"><h3>Discharge Summary</h3>' + (secDischargeSummary(d.discharge_summary, d.details) || U('get_discharge_summary')) + '</div><div class="panel"><h3>Discharge Medications</h3>' + (secMeds(d.discharge_medications) || U('get_discharge_medications')) + '<h3 style="margin-top:16px;">Follow-Up Recommendations</h3>' + (secFollowup(d.followup) || U('get_followup_status')) + '</div></div>');
    out += sv('risk', '<div class="two-col"><div class="panel"><h3>Risk Score</h3>' + (secRisk(d.risk) || U('get_risk_assessment')) + '</div><div class="panel"><h3>Early Intervention &amp; PCP Follow-up</h3>' + (secIntervention(d.intervention, mid, d.followup && d.followup.followup_due) || U('get_intervention_status')) + '</div></div>');
    out += sv('notif', '<div class="panel"><h3>Provider Notification Status &amp; Audit Trail</h3>' + (secNotification(d.provider_notification, d.provider_contacts, mid) || U('get_provider_outreach')) + '</div>');
    out += sv('compare', '<div class="panel"><h3>Side-by-Side Comparison — Prior Admissions (Same Member)</h3>' + (secPrior(d.prior_admissions, Object.assign({}, d.details, d.risk ? {} : {})) || U('get_prior_admissions')) + '</div>');
    out += sv('records', '<div class="panel"><h3>Member Medical Records</h3><div class="panel-sub">Integrated read-only view — EIP / Content Central. Edits must be made at system of record.</div>' + (d.medical_records ? recordRows(d.medical_records.items) : U('get_attachments')) + '</div>');
    return ['<div class="rec-root">' + out + '</div>'];
  }
  function memberSection(b, gaps) {
    var d = b.data, s = b.section, mid = d.member_id, body, title = b.title;
    var map = {
      get_member_trc_status: ['Measure Status', secStatus(d)], get_validation_evidence: ['Attachments & Evidence', secEvidence(d)], get_member_adt_timeline: ['ADT Event History (HL7 v2.5)', secTimeline(d)],
      get_discharge_summary: ['Discharge Summary', secDischargeSummary(d, null)], get_discharge_medications: ['Discharge Medications', secMeds(d)], get_followup_status: ['Follow-Up Recommendations', secFollowup(d)],
      get_risk_assessment: ['Risk Score', secRisk(d)], get_intervention_status: ['Early Intervention', secIntervention(d, mid, null)], get_prior_admissions: ['Prior Admissions', secPrior(d, null)],
      get_provider_outreach: ['Provider Notification Status & Audit Trail', secNotification(d, null, mid)], get_provider_contacts: ['Provider contacts', secContacts(d)],
      get_member_audit_trail: ['Audit Trail', d.events && d.events.length ? '<table><tr><th>When</th><th>Actor</th><th>Action</th><th>Detail</th></tr>' + d.events.map(function (a) { return '<tr><td>' + DT(a.at) + '</td><td>' + E(a.actor) + '</td><td>' + T(a.action) + '</td><td>' + E(a.detail || '') + '</td></tr>'; }).join('') + '</table>' : '<div class="empty">No audit events.</div>'],
      get_member_details: ['Member', detailHeader(d, null)]
    };
    var m = map[s];
    if (m && s === 'get_member_details') return [m[1]];
    if (m) return ['<div class="panel"><h3>' + E(m[0]) + (mid ? ' · ' + E(mid) : '') + '</h3>' + (m[1] || '<div class="empty">No data.</div>') + '</div>'];
    return ['<div class="panel"><h3>' + E(title) + '</h3>' + genericKv(d) + '</div>'];
  }

  /* validation / closure / mrat / records ---------------------------------------------------------------------------------------------- */
  function validationSummary(b) {
    var s = b.data;
    var bars = [['Records uploaded by day 3', s.records_uploaded_by_day3_pct, PAL.amber], ['Claims validated in window', s.claims_validated_pct, PAL.blue], ['Validation passed → soft closed', s.passed_soft_closed_pct, PAL.green], ['Validation failed', s.failed_pct, PAL.red]];
    var chart = panel('Validation Outcomes — Open TRC Proxy Tasks', '', chartBox('bar', function (c) {
      return new Chart(c, { type: 'bar', data: { labels: bars.map(function (x) { return x[0]; }), datasets: [{ label: 'Share of evaluated TRC Proxy Tasks', data: bars.map(function (x) { return x[1]; }), backgroundColor: bars.map(function (x) { return x[2]; }), borderRadius: 6 }] },
        options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { callback: function (v) { return v + '%'; } }, grid: { color: '#eef2f2' } }, x: { grid: { display: false } } }, maintainAspectRatio: false } });
    }));
    var tbl = panel('Validation Agent Summary', '', '<table>' +
      r('TRC Proxy Tasks evaluated (last 90 days)', '<b>' + num(s.evaluated_last_90_days) + '</b>') + r('Provider notified ≤ 1 day of discharge', '<b class="flag-green">' + pct(s.notified_within_1_day_pct) + '</b>') +
      r('Provider records uploaded by day ' + nz(s.window_days, 3), '<b>' + pct(s.records_uploaded_by_day3_pct) + '</b>') + r('Claims validated in ' + nz(s.window_days, 3) + '-day window', '<b>' + pct(s.claims_validated_pct) + '</b>') +
      r('Validation passed → soft closed', '<b class="flag-green">' + pct(s.passed_soft_closed_pct) + '</b>') + r('Validation failed (missing records / claim)', '<b class="flag-red">' + pct(s.failed_pct) + '</b>') +
      r('Avg. time discharge → soft closure', '<b>' + nz(s.avg_days_discharge_to_soft_close) + ' days</b>') + r('Awaiting MRAT final closure', '<b>' + num(s.awaiting_mrat_final_closure) + '</b>') + '</table>');
    function r(k, v) { return '<tr><td>' + k + '</td><td>' + v + '</td></tr>'; }
    return '<div class="two-col" style="margin-bottom:18px;">' + chart + tbl + '</div>';
  }
  function validationRun(b) {
    var d = b.data, res = d.results || [];
    return '<div class="panel"><h3>Validation run ' + E(d.run_id || '') + '</h3><div class="panel-sub">' + num(d.evaluated) + ' evaluated · ' + num(d.passed) + ' passed · ' + num(d.failed) + ' failed' + (d.persisted === false ? ' · not persisted' : '') + '</div>' +
      '<table><tr><th>Member</th><th>Outcome</th><th>Reasons</th><th>Checked</th><th>Action</th></tr>' + res.map(function (x) {
        return '<tr class="anim-row"><td><span class="link-row" data-act="open-member" data-id="' + Aq(x.member_id) + '">' + E(x.member_id) + '</span></td><td>' + outcomeBadge(x.outcome) + '</td><td>' + ((x.reasons || []).map(E).join('<br>') || '—') + '</td><td>' + DT(x.checked_at) + '</td><td>' +
          (x.eligible_for_soft_closure ? '<button class="btn" data-act="ask" data-q="Soft-close ' + Aq(x.member_id) + '">Soft close…</button>' : '<span style="color:var(--trc-muted);font-size:11.5px;">—</span>') + '</td></tr>'; }).join('') + '</table>' +
      lockNote('Soft close is only offered when validation passed. Final MRAT closure is completed by a HEDIS nurse.') + '</div>';
  }
  function closureBoard(b) {
    var cols = b.data.columns || [];
    return '<div class="panel"><h3>TRC Closure Board</h3><div class="panel-sub">Measure status per member · Discharge Identified → Provider Notified → Validation Passed → Soft Closed / MRAT</div><div class="kanban">' + cols.map(function (c) {
      return '<div class="kanban-col"><h4>' + E(c.label) + ' (' + num(c.count) + ')</h4>' + ((c.cards || []).map(function (m) {
        return '<div class="kcard anim-card" data-act="open-member" data-id="' + Aq(m.member_id) + '" style="cursor:pointer;"><div class="kc-name">' + E(m.member_name) + '</div><div class="kc-sub">' + E(m.member_id) + ' · ' + riskBadge(m.risk_tier) + '</div><div class="kc-tag">' + E(m.tag || '') + ' · Follow-up ' + D(m.followup_due) + '</div></div>'; }).join('') || '<div style="color:var(--trc-muted2);font-size:12px;padding:8px;">No members</div>') + '</div>'; }).join('') + '</div></div>';
  }
  function mratStatus(b) {
    var d = b.data;
    return '<div class="panel"><h3>MRAT review status · ' + E(d.member_id) + '</h3>' + kv([['TRC status', trcBadge(d.trc_status)], ['Awaiting final closure', d.awaiting_final_closure ? badge('badge-amber', 'YES') : badge('badge-gray', 'NO')], ['Assigned HEDIS nurse', E(nz(d.assigned_nurse))], ['Closed at', d.closed_at ? DT(d.closed_at) : '—'],
      ['MRAT link', d.mrat_deeplink && /^https:\/\//.test(d.mrat_deeplink) ? '<a href="' + Aq(d.mrat_deeplink) + '" target="_blank" rel="noopener noreferrer">Open in MRAT ↗</a>' : '—']]) +
      lockNote('Final MRAT closure is performed by a HEDIS nurse in MRAT. This assistant cannot close it.') + '</div>';
  }
  function recordsBlock(b) {
    var items = b.data.items || [], members = [];
    items.forEach(function (i) { if (members.indexOf(i.member_name) < 0) members.push(i.member_name); });
    return '<div class="panel"><h3>Consolidated Medical Records Repository</h3><div class="panel-sub">Read-only. "To modify, edit in system of record." All views are audit-logged.' + (members.length === 1 ? ' · ' + E(members[0]) : '') + '</div>' + recordRows(items, members.length > 1) + lockNote('Edit/modify disabled in GuideWell Chat — records are sourced live from EIP and Content Central and remain the system of record.') + '</div>';
  }
  function recordLink(b) {
    var d = b.data;
    return '<div class="panel"><h3>' + E(b.title || 'Record link') + '</h3>' + kv(Object.keys(d).filter(function (k) { return typeof d[k] !== 'object' && !/url|link/i.test(k); }).map(function (k) { return [T(k), E(nz(d[k]))]; })) +
      (d.url && /^https:\/\//.test(d.url) ? '<div style="margin-top:10px"><a class="btn btn-primary" href="' + Aq(d.url) + '" target="_blank" rel="noopener noreferrer">Open read-only ↗</a></div>' : '') + '</div>';
  }
  function providerContacts(b) { return ['<div class="panel">' + secContacts(b.data) + '</div>']; }

  /* ───────────── follow-up suggestions (the mockup's prompt-rec pills) ───────────── */
  function recsFor(reply) {
    var i = String(reply.intent || ''), blocks = reply.blocks || [], mid = null, firstB = blocks[0];
    blocks.forEach(function (b) { if (!mid && b.data && b.data.member_id) mid = b.data.member_id; if (!mid && b.data && b.data.details) mid = b.data.details.member_id; });
    var R = [];
    if (reply.status === 'NEEDS_CONFIRMATION') R = ['Show the TRC closure board', 'How are we doing on TRC? Show the dashboard.'];
    else if (/DASHBOARD/.test(i)) R = ['Show members discharged in the last 14 days where the provider has not uploaded documents by day 3, ranked by risk', 'Which providers have not acknowledged their TRC discharge notifications?', 'Run the validation agent and show the closure board'];
    else if (/WORKLIST/.test(i)) R = [(firstB && firstB.data && firstB.data.items && firstB.data.items[0] ? 'Open the TRC record for ' + firstB.data.items[0].member_id : 'How are we doing on TRC? Show the dashboard.'), 'Which providers have not acknowledged their TRC discharge notifications?', 'Export the no-upload worklist as CSV'];
    else if (/NOTIFICATION/.test(i) && !mid) R = ['Bulk resend to non-responsive providers', 'Run the validation agent and show the closure board'];
    else if (/VALIDATION|CLOSURE/.test(i)) R = ['Show the validation summary', 'Show the TRC closure board', 'Which providers have not acknowledged their TRC discharge notifications?'];
    else if (mid) R = ['Show the MRAT status for ' + mid, 'Show attachments for ' + mid, 'Show the provider notification for ' + mid];
    else if (/^ACTION_|^NO_TOOL/.test(i) || !i) R = ['How are we doing on TRC? Show the dashboard.', 'Show members discharged in the last 14 days where the provider has not uploaded documents by day 3, ranked by risk'];
    else R = ['How are we doing on TRC? Show the dashboard.', 'Show the TRC closure board'];
    return R;
  }
  function recsHtml(reply, idx) {
    var R = recsFor(reply);
    return '<div class="outside-callout"><div class="recs-label">Next</div><div class="prompt-recs">' + R.map(function (q, k) { return '<button class="prompt-rec ' + (k ? 'secondary' : 'primary') + '" data-act="ask" data-q="' + Aq(q) + '">' + ARROW + E(q.length > 90 ? q.slice(0, 88) + '…' : q) + '</button>'; }).join('') + '</div>' +
      '<button class="link-btn" data-act="flow" data-idx="' + idx + '">⇄ Show how this answer was produced (UI → Agent → Gateway → MCP → on-prem)</button></div>';
  }

  /* ───────────── compose ───────────── */
  function compose(reply, p, idx) {
    var out = [], G = group(reply.blocks), gaps = reply.data_gaps || [], used = {};
    if ((reply.tool_trace || []).length) out.push(traceHtml(reply, p));
    var msg = reply.message ? '<p class="prose">' + E(reply.message) + '</p>' : '';
    if (reply.status === 'UNAVAILABLE' || reply.status === 'ERROR') msg = '<p class="prose">' + E(reply.message) + '</p>';
    out.push(msg);
    (reply.warnings || []).forEach(function (w) { out.push('<p class="prose" style="color:#8a5a00">⚠ ' + E(w) + '</p>'); });
    function add(arr) { arr.forEach(function (h) { out.push(h); }); }
    if (G.KPI_SUMMARY) { add(dashboard(G, reply)); used.KPI_SUMMARY = used.METRIC_BREAKDOWN = used.WORKLIST = 1; }
    if (G.VALIDATION_SUMMARY && (G.VALIDATION_RUN || G.CLOSURE_BOARD)) { out.push(validationSummary(G.VALIDATION_SUMMARY[0])); used.VALIDATION_SUMMARY = 1; }
    (reply.blocks || []).forEach(function (b) {
      if (used[b.type]) return;
      switch (b.type) {
        case 'WORKLIST': add(worklistFull(b)); break;
        case 'NOTIFICATIONS': add(notifications(b)); break;
        case 'MEMBER_RECORD': add(memberRecord(b, gaps)); break;
        case 'MEMBER_SECTION': add(memberSection(b, gaps)); break;
        case 'METRIC_BREAKDOWN': out.push(breakdownPanel(b, null)); break;
        case 'VALIDATION_SUMMARY': out.push(validationSummary(b)); break;
        case 'VALIDATION_RUN': out.push(validationRun(b)); break;
        case 'CLOSURE_BOARD': out.push(closureBoard(b)); break;
        case 'MRAT_STATUS': out.push(mratStatus(b)); break;
        case 'RECORDS': out.push(recordsBlock(b)); break;
        case 'RECORD_LINK': out.push(recordLink(b)); break;
        case 'PROVIDER_CONTACTS': add(providerContacts(b)); break;
        case 'ACTION_RESULT': out.push(actionResultCard(b)); break;
        default: out.push('<div class="panel"><h3>' + E(b.title || b.type) + '</h3>' + genericKv(b.data) + '</div>');
      }
    });
    var g = gapsCard(gaps); if (g) out.push(g);
    (reply.pending_actions || []).forEach(function (pa) { out.push(confirmCard(pa)); });
    out.push(recsHtml(reply, idx));
    return out.filter(Boolean);
  }

  /* ───────────── reusable panels (same markup/classes as the mockup's detail view) ───────────── */
  function panel(title, sub, inner, extra) { return '<div class="panel"' + (extra || '') + '><h3>' + E(title) + '</h3>' + (sub ? '<div class="panel-sub">' + sub + '</div>' : '') + inner + '</div>'; }
  function unavailable(what, gaps) {
    var g = (gaps || []).filter(function (x) { return x.section === what || x.tool === what; })[0];
    return '<div class="unavail">⚠ <span>Not available from the data sources right now' + (g ? ' — ' + E(g.message || g.code) : '') + '. Nothing has been inferred.</span></div>';
  }
  function kv(rows) { return '<table class="kv">' + rows.map(function (r) { return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>'; }).join('') + '</table>'; }
  function docItem(name, sub, right) { return '<div class="doc-item"><div><div class="di-name">' + name + '</div><div class="di-sub">' + sub + '</div></div><div>' + right + '</div></div>'; }
  function list(items) { return items && items.length ? '<ul style="margin:6px 0 0 18px;padding:0;">' + items.map(function (f) { return '<li style="margin-bottom:6px;">' + E(f) + '</li>'; }).join('') + '</ul>' : '<div class="empty">None on file.</div>'; }
  function lockNote(t) { return '<div class="lock-note">🔒 ' + t + '</div>'; }

  /* measure status: the five-step funnel with the state the tool reported for each step */
  function secStatus(d) {
    if (!d) return null;
    if (norm(d.trc_status) === 'EXCLUDED') return docItem('Excluded from TRC', E(d.ineligibility_reason || ''), badge('badge-gray', 'EXCLUDED'));
    var steps = d.steps || [];
    if (!steps.length) return '<div class="empty">No step detail returned.</div>';
    return '<div class="doc-list">' + steps.map(function (s) {
      var st = norm(s.state), done = st === 'DONE', fail = st === 'FAILED', prog = st === 'IN_PROGRESS';
      var dot = fail ? 'dot-red' : done ? 'dot-green' : prog ? 'dot-amber' : '';
      var cls = fail ? 'badge-red' : done ? 'badge-green' : prog ? 'badge-amber' : 'badge-gray';
      return '<div class="doc-item"><div><div class="di-name"><span class="status-dot ' + dot + '" style="' + (dot ? '' : 'background:#d5dede;') + '"></span>' + E(s.label) + '</div><div class="di-sub">' + E(s.detail || '') + '</div></div>' + badge(cls, fail ? 'FAILED' : done ? 'DONE' : prog ? 'IN PROGRESS' : 'PENDING') + '</div>';
    }).join('') + '</div>';
  }
  function secEvidence(v) {
    if (!v) return null;
    var items = (v.items || []).map(function (e) { return docItem(E(e.name), E(e.source_system || '') + (e.detail ? ' · ' + E(e.detail) : ''), badge(e.available ? 'badge-green' : 'badge-red', e.available ? 'Available' : 'Missing')); }).join('');
    var rule = norm(v.rule_outcome);
    var facts = kv([
      ['Validation rule outcome', rule ? outcomeBadge(rule) : '—'],
      ['Window', E(nz(v.window_days)) + ' days post-discharge'],
      ['Provider Vista upload', uploadBadge(v.upload_status, v.upload_date)],
      ['Claim', badge(norm(v.claim_status) === 'MATCHED' ? 'badge-green' : 'badge-red', T(nz(v.claim_status))) + (v.claim_date ? ' ' + D(v.claim_date) : '')],
      ['Care Navi task', T(nz(v.care_navi_task_status))]
    ]);
    return '<div class="doc-list">' + items + '</div><div style="margin-top:12px">' + facts + '</div>';
  }
  function secTimeline(t) {
    if (!t) return null;
    var ev = t.events || [];
    if (!ev.length) return '<div class="empty">No ADT events returned.</div>';
    return '<div class="timeline">' + ev.map(function (e) {
      var cls = /A03/.test(e.event_type) ? 'discharge' : /A11|A13|A12/.test(e.event_type) ? 'cancel' : '';
      return '<div class="tl-item ' + cls + '"><div class="tl-dot"></div><span class="tl-code">' + E(e.event_type) + ' — ' + E(e.label) + '</span><span class="tl-when">' + DT(e.occurred_at) + '</span>' +
        (e.location ? '<div class="tl-desc">📍 ' + E(e.location) + '</div>' : '') + (e.detail ? '<div class="tl-detail">' + E(e.detail) + '</div>' : '') +
        (e.raw_hl7 ? '<span class="raw-toggle" data-act="raw">▸ view raw HL7 v2.5 segment</span><div class="raw-hl7">' + E(e.raw_hl7) + '</div>' : '') + '</div>';
    }).join('') + '</div>';
  }
  function secDischargeSummary(ds, details) {
    if (!ds && !details) return null;
    var dx = ds ? nz(ds.diagnosis_code, '') + (ds.diagnosis_description ? ' — ' + ds.diagnosis_description : '') : '';
    return '<table class="kv"><tr><td>Discharge Diagnosis</td><td><b>' + E(dx || '—') + '</b></td></tr>' +
      '<tr><td>Disposition</td><td><b>' + T(ds && ds.disposition) + '</b></td></tr>' +
      '<tr><td>Discharging Facility</td><td>' + E(nz(ds && ds.facility)) + '</td></tr>' +
      '<tr><td>Source Documents</td><td>' + (ds && ds.source_documents && ds.source_documents.length ? ds.source_documents.map(E).join('<br>') : '—') + '</td></tr>' +
      '<tr><td>Last Updated</td><td>' + DT(ds && ds.last_updated) + '</td></tr></table>';
  }
  function secMeds(m) {
    if (!m) return null;
    var rows = (m.medications || []).map(function (r) { return '<tr><td>' + E(r.name) + '</td><td>' + E(r.dose) + '</td><td>' + E(r.frequency) + '</td><td>' + E(r.indication) + '</td></tr>'; }).join('');
    return '<table class="med-table"><tr><th>Medication</th><th>Dose</th><th>Freq.</th><th>Indication</th></tr>' + (rows || '<tr><td colspan="4" class="empty">No discharge medications on file</td></tr>') + '</table>';
  }
  function secFollowup(f) {
    if (!f) return null;
    var due = f.followup_due ? '<div style="margin-bottom:8px">PCP follow-up due <b>' + D(f.followup_due) + '</b> ' +
      (f.overdue ? badge('badge-red', 'OVERDUE ' + Math.abs(f.days_until_due) + 'd') : f.days_until_due !== null && f.days_until_due !== undefined ? badge('badge-blue', 'in ' + f.days_until_due + 'd') : '') + ' ' +
      (f.pcp_visit_confirmed ? badge('badge-green', 'VISIT CONFIRMED') : badge('badge-amber', 'VISIT NOT CONFIRMED')) + '</div>' : '';
    return due + list(f.recommendations);
  }
  function secRisk(r) {
    if (!r) return null;
    return '<div class="kpi-card" style="margin-bottom:12px;"><div class="lbl">AI Risk Score (prioritization)</div><div class="val">' + Math.round((r.score || 0) * 100) + '% ' + riskBadge(r.tier) + '</div></div>' +
      '<div class="k" style="font-size:11px;color:var(--trc-muted);font-weight:700;text-transform:uppercase;margin-bottom:6px;">Contributing Factors</div>' + list(r.factors) +
      (r.model_note ? '<div class="lock-note">ⓘ ' + E(r.model_note) + '</div>' : '');
  }
  function secIntervention(i, memberId, fu) {
    if (!i) return null;
    var acts = (i.activities || []).map(function (a) { return a.description || a; });
    return '<div style="margin-bottom:10px;">' + intBadge(i.status) + ' <span style="font-size:12.5px;color:var(--trc-muted);margin-left:8px;">Coordinator: ' + E(nz(i.coordinator)) + (i.due_date ? ' · due ' + D(i.due_date) : '') + (fu ? ' · PCP follow-up due ' + D(fu) : '') + '</span></div>' +
      '<div class="k" style="font-size:11px;color:var(--trc-muted);font-weight:700;text-transform:uppercase;margin-bottom:6px;">Activity Log</div>' + list(acts) +
      '<div><button class="btn btn-primary" style="margin-top:10px;" data-act="log-form">+ Log Intervention Activity</button>' +
      '<div class="inline-form" style="display:none"><input type="text" maxlength="500" placeholder="Describe the activity (a confirmation card will follow)"><button class="btn btn-primary" data-act="log-send" data-id="' + Aq(memberId) + '">Review</button></div></div>';
  }
  function secNotification(n, contacts, memberId) {
    if (!n) return null;
    var rows = kv([
      ['Status', notifBadge(n.status)], ['Channel', T(nz(n.channel))], ['Sent To', E(nz(n.provider_name))], ['Sent At', DT(n.sent_at)],
      ['Acknowledged At', n.acknowledged_at ? DT(n.acknowledged_at) : '—'], ['Provider Response', badge('badge-blue', T(nz(n.provider_response)))],
      ['Alert Contents', (n.alert_fields || []).map(E).join(', ') || '—'], ['Proxy Task Updated', n.proxy_task_updated ? 'Yes' : 'No'],
      ['Provider Vista Upload', uploadBadge(n.vista_upload, n.vista_upload_date)]
    ]);
    var audit = (n.audit_trail || []).length ? '<h3 style="margin:16px 0 8px;font-size:13px">Audit trail</h3><table><tr><th>When</th><th>Actor</th><th>Action</th><th>Detail</th></tr>' + n.audit_trail.map(function (a) { return '<tr><td>' + DT(a.at) + '</td><td>' + E(a.actor) + '</td><td>' + T(a.action) + '</td><td>' + E(a.detail || '') + '</td></tr>'; }).join('') + '</table>' : '';
    var canResend = ['FAILED', 'PENDING'].indexOf(norm(n.status)) >= 0;
    var btns = '<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;">' +
      '<button class="btn" data-act="ask" data-q="Resend the provider alert for ' + Aq(memberId) + '"' + (canResend ? '' : ' disabled title="Resend is only allowed for FAILED or PENDING alerts"') + '>🔁 Resend Notification</button>' +
      '<button class="btn" data-act="ask" data-q="Escalate ' + Aq(memberId) + ' to the provider manager">⚠ Escalate to Provider Manager</button>' +
      '<button class="btn" data-act="ask" data-q="Show the audit trail for ' + Aq(memberId) + '">📜 View Full Audit Trail</button></div>';
    return rows + audit + btns + (contacts ? secContacts(contacts) : '');
  }
  function secContacts(c) {
    if (!c) return '';
    return '<h3 style="margin:18px 0 8px;font-size:13px">Verified provider contacts — ' + E(c.provider_name) + (c.specialty ? ' · ' + E(c.specialty) : '') + '</h3><div class="doc-list">' +
      (c.contacts || []).map(function (x) { return docItem(T(x.channel) + (x.preferred ? ' ' + badge('badge-blue', 'PREFERRED') : ''), E(x.value) + (x.verified_on ? ' · verified ' + D(x.verified_on) : ''), badge(x.verified ? 'badge-green' : 'badge-amber', x.verified ? 'Verified' : 'Unverified')); }).join('') + '</div>';
  }
  function secPrior(p, d) {
    if (!p) return null;
    var a = p.admissions || [], cur = d || {};
    var dx = cur.diagnosis_description ? cur.diagnosis_description : '—';
    var rows = [
      ['Admit → Discharge', cur.admit_at ? D(cur.admit_at) + ' → ' + D(cur.discharge_at) : '—', a[0] ? D(a[0].admit_date) + ' → ' + D(a[0].discharge_date) : '—', a[1] ? D(a[1].admit_date) + ' → ' + D(a[1].discharge_date) : '—'],
      ['Facility', E(nz(cur.facility)), E(a[0] ? a[0].facility : '—'), E(a[1] ? a[1].facility : '—')],
      ['Diagnosis', E(dx), E(a[0] ? first(a[0].diagnosis) : '—'), E(a[1] ? first(a[1].diagnosis) : '—')],
      ['Disposition', T(nz(cur.disposition)), T(a[0] ? a[0].disposition : '—'), T(a[1] ? a[1].disposition : '—')],
      ['TRC Outcome', T(nz(cur.trc_status)), T(a[0] ? a[0].trc_outcome : '—'), T(a[1] ? a[1].trc_outcome : '—')]
    ];
    if (!a.length) return '<div class="empty">No prior admissions on file.</div>';
    return '<table><tr><th></th><th>Current Admission</th><th>Prior Admission (-1)</th><th>Prior Admission (-2)</th></tr>' + rows.map(function (r) { return '<tr><td style="color:var(--trc-muted);font-weight:700;">' + r[0] + '</td><td>' + r[1] + '</td><td>' + r[2] + '</td><td>' + r[3] + '</td></tr>'; }).join('') + '</table>';
  }
  function recordRows(items, showMember) {
    if (!items || !items.length) return '<div class="empty">No records returned.</div>';
    return '<div class="doc-list">' + items.map(function (r) {
      var ok = norm(r.status) === 'COMPLETE';
      return '<div class="doc-item"><div><div class="di-name">' + E(r.name) + '</div><div class="di-sub">' + T(r.record_type) + ' · Source: ' + T(r.source) + ' · ' + D(r.date) + (showMember && r.member_name ? ' · ' + E(r.member_name) : '') + '</div></div>' +
        '<div>' + badge(ok ? 'badge-green' : 'badge-amber', T(r.status)) + ' <button class="btn" style="margin-left:8px;" data-act="ask" data-q="Get the access link for attachment ' + Aq(r.attachment_id) + '">View 🔒</button></div></div>';
    }).join('') + '</div>';
  }
  function detailHeader(d, risk) {
    if (!d) return '';
    var dx = (d.diagnosis_code || '') + (d.diagnosis_description ? ' — ' + d.diagnosis_description : '');
    return '<div class="detail-header"><div><div class="dh-name">' + E(d.name) + '</div>' +
      '<div class="dh-meta">' + E(d.member_id) + ' · MRN ' + E(nz(d.mrn)) + ' · DOB ' + D(d.dob) + (d.age !== undefined && d.age !== null ? ' (age ' + d.age + ')' : '') + ' · ' + (d.gender === 'F' ? 'Female' : d.gender === 'M' ? 'Male' : E(nz(d.gender))) + ' · ' + T(nz(d.line_of_business)) + '</div>' +
      '<div class="dh-grid">' +
      f('Admit Date', DT(d.admit_at)) + f('Discharge Date', DT(d.discharge_at)) + f('Facility', E(nz(d.facility))) + f('Facility Type', T(nz(d.facility_type))) +
      f('Admission Type', T(nz(d.admission_type))) + f('Diagnosis', E(dx || '—')) + f('Disposition', T(nz(d.disposition))) +
      f('Eligibility', T(nz(d.eligibility)) + (d.ineligibility_reason ? ' <span style="font-weight:400;color:var(--trc-muted);">— ' + E(d.ineligibility_reason) + '</span>' : '')) +
      '</div></div><div style="text-align:right;">' + (risk ? riskBadge(risk.tier) + '<br><br>' : '') + trcBadge(d.trc_status) + '</div></div>';
    function f(k, v) { return '<div class="dh-field"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>'; }
  }
  function genericKv(d) {
    var rows = Object.keys(d || {}).filter(function (k) { return k !== 'member_id' && typeof d[k] !== 'object'; }).map(function (k) { return [T(k), E(nz(d[k]))]; });
    return rows.length ? kv(rows) : '<div class="empty">No fields returned.</div>';
  }

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
