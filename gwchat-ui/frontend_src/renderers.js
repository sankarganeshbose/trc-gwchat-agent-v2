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
