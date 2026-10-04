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
