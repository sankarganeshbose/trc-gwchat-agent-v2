"""In-memory, stateful stand-in for the on-prem TRC APIs, seeded from the GWChat prototype's mock members.

It returns the *assumed on-prem DTO shape* (camelCase), exactly like the real HTTP client would, so the same mappers,
tools and agent run unchanged against it. It also enforces the business rules the real services are assumed to own
(resend only FAILED/PENDING, soft-close only after validation passed) so write-path behaviour can be tested.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from importlib import resources
from typing import Any, Mapping

from trc_contracts.common import ErrorCode

from ..config import Settings
from ..errors import OnPremError
from .base import CallContext, Op

AGG = {
    "summary": {
        "measurementPeriod": "2026-01-01/2026-12-31", "dischargesIdentified": 1284,
        "providerNotified": {"count": 1233, "ratePct": 96.0}, "validationPassed": {"count": 812, "ratePct": 63.2},
        "softClosed": {"count": 745, "ratePct": 58.0}, "mratFinalClosed": 512, "noUploadByDay3": 37,
        "noUploadByDay3HighRisk": 23, "awaitingMratClosure": 61, "closureRatePct": 58.0,
        "priorQuarterClosureRatePct": 52.4, "planTargetPct": 60.0, "activeWindowMembers": 284,
        "riskTiers": [
            {"tier": "HIGH", "count": 23, "note": "Past day 3, no provider upload: 23"},
            {"tier": "MEDIUM", "count": 54, "note": "Notified, awaiting records: 31"},
            {"tier": "LOW", "count": 207, "note": "Routine follow-up only"},
        ],
    },
    "metrics": {
        "COMPONENT": [("Notification of Inpatient Admission", 1284, 71.4), ("Receipt of Discharge Information", 1284, 63.2),
                      ("Patient Engagement After Inpatient Discharge", 1284, 82.6),
                      ("Medication Reconciliation Post-Discharge", 1284, 68.9)],
        "FACILITY": [("Baptist Health Jacksonville", 241, 51.0), ("UF Health Shands Hospital", 198, 47.5),
                     ("AdventHealth Orlando", 233, 44.2), ("Tampa General Hospital", 211, 41.7),
                     ("Orlando Regional Medical Center", 177, 38.4), ("Memorial Hospital Miramar", 129, 35.7),
                     ("Mayo Clinic Florida", 95, 31.6)],
        "DISPOSITION": [("Home", None, 58), ("Home w/ Services", None, 21), ("SNF", None, 12), ("Rehab", None, 5),
                        ("Acute Transfer", None, 2), ("Hospice", None, 1), ("Expired", None, 1)],
        "TREND": list(zip(["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"], [None] * 12,
                          [41.2, 42.8, 44.1, 45.0, 46.3, 48.9, 50.2, 51.7, 52.4, 54.8, 56.3, 58.0])),
    },
    "validationSummary": {"windowDays": 3, "evaluatedLast90Days": 460, "notifiedWithin1DayPct": 96.0,
                          "uploadedByDay3Pct": 71.3, "claimsValidatedPct": 64.1, "passedSoftClosedPct": 58.0,
                          "failedPct": 12.4, "avgDaysToSoftClose": 2.6, "awaitingMratFinalClosure": 61},
}
BOARD_LABELS = {"DISCHARGE_IDENTIFIED": "Discharge Identified", "PROVIDER_NOTIFIED": "Provider Notified",
                "VALIDATION_PASSED": "Validation Passed", "SOFT_CLOSED": "Soft Closed / MRAT"}
ALERT_FIELDS = ["Member", "Admit/discharge type & date", "Provider", "Required HEDIS fields"]


def _err(code: ErrorCode, msg: str, status: int, **details: Any) -> OnPremError:
    return OnPremError(code, msg, upstream_status=status, details=details)


class StubOnPremClient:
    def __init__(self, settings: Settings):
        raw = resources.files("trc_mcp.clients").joinpath("fixtures/members.json").read_text()
        self.members: list[dict] = json.loads(raw)
        self.today = date.fromisoformat(settings.stub_as_of)
        self.now = datetime.combine(self.today, datetime.min.time()).replace(hour=9)
        self.idem: dict[str, tuple[str, Any]] = {}
        self.audit: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []  # test hook: (op, tool)
        self.fail_next: dict[Op, OnPremError] = {}  # test hook for fault injection

    async def aclose(self) -> None:
        return None

    # ───────────────────────── dispatch ─────────────────────────
    async def call(self, op: Op, *, ctx: CallContext, path: Mapping[str, str] | None = None,
                   query: Mapping[str, Any] | None = None, body: Mapping[str, Any] | None = None) -> Any:
        self.calls.append((op.value, ctx.tool))
        if op in self.fail_next:
            raise self.fail_next.pop(op)
        handler = getattr(self, f"_h_{op.value.lower()}")
        return copy.deepcopy(handler(ctx, path or {}, query or {}, body or {}))

    # ───────────────────────── helpers ─────────────────────────
    def _m(self, member_id: str) -> dict:
        for m in self.members:
            if m["memberId"] == member_id:
                return m
        raise _err(ErrorCode.NOT_FOUND, "Member not found.", 404)

    def _days_since(self, m: dict) -> int:
        return (self.today - date.fromisoformat(m["dischargeAt"][:10])).days

    def _past3(self, m: dict) -> bool:
        return (m["eligibility"]["status"] == "ELIGIBLE" and m["trc"]["upload"]["status"] == "NOT_UPLOADED"
                and self._days_since(m) > 3 and m["trc"]["status"] not in ("MRAT_CLOSED", "SOFT_CLOSED"))

    def _row(self, m: dict) -> dict:
        n = m["notification"]
        return {
            "memberId": m["memberId"], "name": m["name"], "lineOfBusiness": m["lineOfBusiness"],
            "admitAt": m["admitAt"], "dischargeAt": m["dischargeAt"], "facility": m["facility"],
            "diagnosis": m["diagnosis"], "disposition": m["disposition"], "eligibility": m["eligibility"]["status"],
            "trcStatus": m["trc"]["status"], "riskScore": m["risk"]["score"], "riskTier": m["risk"]["tier"],
            "notificationStatus": n["status"], "notificationChannel": n["channel"],
            "uploadStatus": m["trc"]["upload"]["status"], "followupDue": m["trc"]["followupDue"],
            "daysSinceDischarge": self._days_since(m), "pastDay3NoUpload": self._past3(m),
        }

    def _idem(self, ctx: CallContext, payload: Any, fn):
        key = ctx.idempotency_key
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        if key and key in self.idem:
            prev_digest, prev = self.idem[key]
            if prev_digest != digest:
                raise _err(ErrorCode.CONFLICT, "Idempotency key reused with a different payload.", 409)
            return {**prev, "idempotentReplay": True}
        result = fn()
        if key:
            self.idem[key] = (digest, result)
        return result

    def _log(self, member_id: str, ctx: CallContext, action: str, detail: str | None = None) -> None:
        self.audit.setdefault(member_id, []).append(
            {"at": self.now.isoformat(), "actor": ctx.principal.user_id, "action": action, "detail": detail})

    # ───────────────────────── cohort ─────────────────────────
    def _h_get_summary(self, ctx, path, q, b):
        return AGG["summary"]

    def _h_get_metrics(self, ctx, path, q, b):
        dim = path["dimension"].upper()
        if dim not in AGG["metrics"]:
            raise _err(ErrorCode.INVALID_ARGUMENT, "Unknown metric dimension.", 400)
        unit = "percent"
        return {"dimension": dim, "measurementPeriod": AGG["summary"]["measurementPeriod"], "unit": unit,
                "points": [{"label": l, "denominator": d, "value": v} for l, d, v in AGG["metrics"][dim]]}

    def _h_get_worklist(self, ctx, path, q, b):
        rows = list(self.members)
        text = (q.get("q") or "").lower()
        if text:
            rows = [m for m in rows if text in m["name"].lower() or text in m["memberId"].lower() or text in m["mrn"].lower()]
        for key, fn in {
            "eligibility": lambda m: m["eligibility"]["status"], "disposition": lambda m: m["disposition"],
            "trcStatus": lambda m: m["trc"]["status"], "uploadStatus": lambda m: m["trc"]["upload"]["status"],
            "riskTier": lambda m: m["risk"]["tier"], "facility": lambda m: m["facility"],
            "lineOfBusiness": lambda m: m["lineOfBusiness"],
        }.items():
            if q.get(key):
                rows = [m for m in rows if fn(m) == q[key]]
        if q.get("lookbackDays") is not None:
            rows = [m for m in rows if self._days_since(m) <= int(q["lookbackDays"])]
        if q.get("dischargeFrom"):
            rows = [m for m in rows if m["dischargeAt"][:10] >= q["dischargeFrom"]]
        if q.get("dischargeTo"):
            rows = [m for m in rows if m["dischargeAt"][:10] <= q["dischargeTo"]]
        if q.get("pastDay3Only"):
            rows = [m for m in rows if self._past3(m)]
        field, _, direction = (q.get("sort") or "riskScore:desc").partition(":")
        keyfn = {"riskScore": lambda m: m["risk"]["score"], "dischargeDate": lambda m: m["dischargeAt"],
                 "followupDue": lambda m: m["trc"]["followupDue"] or "9999"}[field]
        rows.sort(key=keyfn, reverse=(direction != "asc"))
        total = len(rows)
        off = int(q.get("cursor") or 0)
        lim = int(q.get("limit") or 25)
        page = rows[off: off + lim]
        nxt = str(off + lim) if off + lim < total else None
        return {"items": [self._row(m) for m in page], "total": total, "nextCursor": nxt}

    def _h_get_closure_board(self, ctx, path, q, b):
        cols = []
        for status, label in BOARD_LABELS.items():
            cards = []
            for m in self.members:
                s = "SOFT_CLOSED" if m["trc"]["status"] == "MRAT_CLOSED" else m["trc"]["status"]
                if s != status:
                    continue
                t = m["trc"]
                tag = ("MRAT closed" if t["status"] == "MRAT_CLOSED" else "Awaiting MRAT" if t["status"] == "SOFT_CLOSED"
                       else "Records uploaded" if t["upload"]["status"] == "UPLOADED" else "No Vista upload")
                cards.append({"memberId": m["memberId"], "name": m["name"], "riskTier": m["risk"]["tier"],
                              "trcStatus": t["status"], "tag": tag, "followupDue": t["followupDue"]})
            cols.append({"status": status, "label": label, "count": len(cards), "cards": cards})
        return {"columns": cols}

    # ───────────────────────── member ─────────────────────────
    def _h_get_member(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        return {k: m[k] for k in ("memberId", "name", "dob", "age", "gender", "mrn", "lineOfBusiness", "admitAt",
                                  "dischargeAt", "facility", "facilityType", "admissionType", "diagnosis",
                                  "disposition", "eligibility")} | {"trcStatus": m["trc"]["status"],
                                                                     "followupDue": m["trc"]["followupDue"]}

    def _h_get_trc_status(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        t, n = m["trc"], m["notification"]
        base = {"memberId": m["memberId"], "status": t["status"], "eligibility": m["eligibility"], "followupDue": t["followupDue"]}
        if t["status"] == "EXCLUDED":
            return base | {"steps": []}
        order = ["DISCHARGE_IDENTIFIED", "PROVIDER_NOTIFIED", "VALIDATION_PASSED", "SOFT_CLOSED", "MRAT_CLOSED"]
        labels = ["Discharge Identified", "Provider Notified", "Validation Passed", "Soft Closed", "MRAT Final Closure"]
        cur = order.index(t["status"])
        up, cl = t["upload"], t["claim"]
        details = [
            f"ADT A03 received {m['dischargeAt'][:10]} · Proxy Task opened",
            (f"Alert FAILED via {n['channel']} — resend required" if n["status"] == "FAILED"
             else f"Alert {n['status'].lower()} via {n['channel']} · {n['sentAt']}"),
            f"Vista upload: {up['status']}{' (' + up['date'] + ')' if up.get('date') else ''} · Claim: {cl['status']}{' (' + cl['date'] + ')' if cl.get('date') else ''} · 3-day window",
            "Task update & soft closure", "HEDIS nurse human-in-the-loop validation in MRAT"]
        steps = []
        for i, (k, lab, det) in enumerate(zip(order, labels, details)):
            failed = i == 1 and n["status"] == "FAILED"
            state = "FAILED" if failed else "DONE" if i <= cur else "IN_PROGRESS" if i == cur + 1 else "PENDING"
            steps.append({"key": k, "label": lab, "state": state, "detail": det})
        return base | {"steps": steps}

    def _h_get_adt_events(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        ev = m["adtEvents"]
        if not q.get("includeRawHl7"):
            ev = [{k: v for k, v in e.items() if k != "rawHl7"} for e in ev]
        return {"memberId": m["memberId"], "events": ev}

    def _h_get_discharge(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        docs = sorted({f"{r['type']} ({r['source']})" for r in m["records"]})
        return {"memberId": m["memberId"], "diagnosis": m["diagnosis"], "disposition": m["disposition"],
                "facility": m["facility"], "sourceDocuments": docs, "lastUpdated": m["dischargeAt"]}

    def _h_get_discharge_meds(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        return {"memberId": m["memberId"], "medications": m["medications"]}

    def _h_get_followup(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        due = m["trc"]["followupDue"]
        due = due if due and due[0].isdigit() else None  # prototype uses '—' for excluded members
        delta = (date.fromisoformat(due) - self.today).days if due else None
        return {"memberId": m["memberId"], "followupDue": due, "daysUntilDue": delta,
                "recommendations": m["followupRecommendations"],
                "pcpVisitConfirmed": m["notification"]["response"] == "APPOINTMENT_CONFIRMED"}

    def _h_get_risk(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        return {"memberId": m["memberId"], **m["risk"]}

    def _h_get_intervention(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        return {"memberId": m["memberId"], **m["intervention"]}

    def _h_get_prior_admissions(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        return {"memberId": m["memberId"], "admissions": m["priorAdmissions"]}

    def _h_get_audit(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        n = m["notification"]
        ev = [{"at": n["sentAt"], "actor": "Notification Processor", "action": f"ALERT_{n['status']}",
               "detail": f"via {n['channel']}"}]
        if n["ackedAt"]:
            ev.append({"at": n["ackedAt"], "actor": n["provider"]["name"], "action": "ACKNOWLEDGED", "detail": n["response"]})
        return {"memberId": m["memberId"], "events": ev + self.audit.get(m["memberId"], [])}

    # ───────────────────────── provider / notification ─────────────────────────
    def _h_get_provider_contacts(self, ctx, path, q, b):
        for m in self.members:
            p = m["notification"]["provider"]
            if p["providerId"] == path["providerId"]:
                return {"providerId": p["providerId"], "name": p["name"], "specialty": p["specialty"], "contacts": [
                    {"channel": "FAX", "value": "fax ***-***-4410", "verified": True, "verifiedOn": "2026-05-14", "preferred": True},
                    {"channel": "EMAIL", "value": "d***@clinic.example", "verified": True, "verifiedOn": "2026-03-02", "preferred": False},
                    {"channel": "PROVIDER_PROXY_TASK", "value": None, "verified": True, "verifiedOn": "2026-01-20", "preferred": False}]}
        raise _err(ErrorCode.NOT_FOUND, "Provider not found.", 404)

    def _outreach(self, m: dict) -> dict:
        n = m["notification"]
        return {"memberId": m["memberId"], "notificationId": n["notificationId"], "provider": n["provider"],
                "event": "Discharge (A03)", "status": n["status"], "channel": n["channel"], "sentAt": n["sentAt"],
                "ackedAt": n["ackedAt"], "response": n["response"], "uploadStatus": m["trc"]["upload"]["status"],
                "uploadDate": m["trc"]["upload"].get("date"), "alertFields": ALERT_FIELDS, "proxyTaskUpdated": True}

    def _h_get_notification(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        out = self._outreach(m)
        out["auditTrail"] = self._h_get_audit(ctx, path, {}, {})["events"]
        return out

    def _h_list_notifications(self, ctx, path, q, b):
        rows = [m for m in self.members if m["eligibility"]["status"] == "ELIGIBLE"]
        if q.get("status"):
            rows = [m for m in rows if m["notification"]["status"] == q["status"]]
        if q.get("channel"):
            rows = [m for m in rows if m["notification"]["channel"] == q["channel"]]
        if q.get("facility"):
            rows = [m for m in rows if m["facility"] == q["facility"]]
        if q.get("response"):
            rows = [m for m in rows if m["notification"]["response"] == q["response"]]
        if q.get("unacknowledged"):
            rows = [m for m in rows if m["notification"]["status"] != "ACKNOWLEDGED"]
        lim = int(q.get("limit") or 25)
        return {"items": [self._outreach(m) | {"memberName": m["name"], "facility": m["facility"]} for m in rows[:lim]],
                "total": len(rows)}

    def _resend(self, ctx: CallContext, member_id: str, channel: str | None) -> dict:
        m = self._m(member_id)
        n = m["notification"]
        if n["status"] not in ("FAILED", "PENDING"):
            raise _err(ErrorCode.PRECONDITION_FAILED, "Only FAILED or PENDING alerts can be resent.", 422, upstream_code="RESEND_NOT_ALLOWED")
        n.update(status="SENT", channel=channel or n["channel"], sentAt=self.now.isoformat(), response="PENDING_RESPONSE")
        self._log(member_id, ctx, "ALERT_RESENT", n["channel"])
        return {"notificationId": n["notificationId"], "memberId": member_id, "status": "SENT",
                "channel": n["channel"], "proxyTaskUpdated": True, "idempotentReplay": False}

    def _h_send_notification(self, ctx, path, q, b):
        return self._idem(ctx, b, lambda: self._resend(ctx, b["memberId"], b.get("channel")))

    def _h_bulk_resend_notifications(self, ctx, path, q, b):
        def run():
            accepted, skipped = [], []
            for mid in b["memberIds"]:
                try:
                    accepted.append(self._resend(ctx, mid, None))
                except OnPremError as e:
                    skipped.append({"memberId": mid, "reason": e.details.get("upstream_code") or e.message})
            return {"batchId": f"BLK-{uuid.uuid4().hex[:8]}", "requested": len(b["memberIds"]), "accepted": accepted,
                    "skipped": skipped}
        return self._idem(ctx, b, run)

    def _h_create_escalation(self, ctx, path, q, b):
        def run():
            m = self._m(b["memberId"])
            self._log(m["memberId"], ctx, "ESCALATED_TO_PROVIDER_MANAGER", b.get("reason"))
            return {"escalationId": f"ESC-{uuid.uuid4().hex[:8]}", "memberId": m["memberId"],
                    "notificationId": m["notification"]["notificationId"], "escalatedTo": f"Provider Manager — {m['facility']}"}
        return self._idem(ctx, b, run)

    # ───────────────────────── validation / closure / records ─────────────────────────
    def _evaluate(self, m: dict) -> dict:
        t, reasons = m["trc"], []
        if m["eligibility"]["status"] != "ELIGIBLE":
            return {"memberId": m["memberId"], "outcome": "FAILED", "reasons": ["Member ineligible for TRC"], "checkedAt": self.now.isoformat()}
        if t["upload"]["status"] != "UPLOADED":
            reasons.append("No Provider Vista / Link upload")
        if t["claim"]["status"] != "MATCHED":
            reasons.append(f"Claim {t['claim']['status'].replace('_', ' ').lower()} in 3-day window")
        outcome = "PASSED" if not reasons else ("FAILED" if self._days_since(m) > 3 else "PENDING")
        return {"memberId": m["memberId"], "outcome": outcome, "reasons": reasons, "checkedAt": self.now.isoformat(),
                "eligibleForSoftClosure": outcome == "PASSED" and t["status"] in ("PROVIDER_NOTIFIED", "VALIDATION_PASSED")}

    def _h_get_validation(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        t, n = m["trc"], m["notification"]
        res = self._evaluate(m)
        return {"memberId": m["memberId"], "windowDays": 3, "upload": t["upload"], "claim": t["claim"],
                "careNaviTaskStatus": m["intervention"]["status"], "ruleOutcome": res["outcome"],
                "items": [
                    {"name": "Discharge Summary (PDF)", "sourceSystem": "ADT/HIE", "available": True, "detail": m["facility"]},
                    {"name": "Provider Notification (PDF)", "sourceSystem": "Notification Processor", "available": n["status"] != "FAILED", "detail": f"{n['channel']} · {n['provider']['name']}"},
                    {"name": "Provider Medical Records", "sourceSystem": "Provider Vista / Link", "available": t["upload"]["status"] == "UPLOADED", "detail": t["upload"].get("date")},
                    {"name": "Claim Match (PDF)", "sourceSystem": "Claims", "available": t["claim"]["status"] == "MATCHED", "detail": t["claim"].get("date")}]}

    def _h_get_validation_summary(self, ctx, path, q, b):
        return AGG["validationSummary"]

    def _h_run_claim_validation(self, ctx, path, q, b):
        ids = b.get("memberIds")
        targets = [self._m(i) for i in ids] if ids else [m for m in self.members if m["trc"]["status"] not in ("MRAT_CLOSED", "EXCLUDED")]
        results = [self._evaluate(m) for m in targets]
        for r in results:
            r.setdefault("eligibleForSoftClosure", False)
        return {"runId": f"VAL-{uuid.uuid4().hex[:8]}", "results": results, "persisted": bool(b.get("persist", True))}

    def _h_get_attachments(self, ctx, path, q, b):
        out = []
        for m in self.members:
            if q.get("memberId") and m["memberId"] != q["memberId"]:
                continue
            for r in m["records"]:
                if q.get("recordType") and r["type"] != q["recordType"]:
                    continue
                if q.get("source") and r["source"] != q["source"]:
                    continue
                out.append({**r, "memberId": m["memberId"], "memberName": m["name"]})
        if q.get("memberId"):
            self._log(q["memberId"], ctx, "RECORD_LIST_VIEWED", "attachments")
        return {"items": out[: int(q.get("limit") or 50)], "total": len(out)}

    def _h_create_attachment_link(self, ctx, path, q, b):
        aid = path["attachmentId"]
        for m in self.members:
            if any(r["attachmentId"] == aid for r in m["records"]):
                self._log(m["memberId"], ctx, "RECORD_ACCESSED", aid)
                return {"attachmentId": aid, "url": f"https://viewer.onprem.guidewell.example/doc/{aid}?t={uuid.uuid4().hex[:12]}",
                        "expiresAt": (self.now + timedelta(minutes=10)).isoformat()}
        raise _err(ErrorCode.NOT_FOUND, "Attachment not found.", 404)

    def _h_get_mrat_status(self, ctx, path, q, b):
        m = self._m(path["memberId"])
        s = m["trc"]["status"]
        return {"memberId": m["memberId"], "trcStatus": s, "awaitingFinalClosure": s == "SOFT_CLOSED",
                "assignedNurse": "HEDIS Nurse Pool A" if s in ("SOFT_CLOSED", "MRAT_CLOSED") else None,
                "mratDeeplink": f"https://mrat.onprem.guidewell.example/review/{m['memberId']}" if s in ("SOFT_CLOSED", "MRAT_CLOSED") else None,
                "closedAt": self.now.isoformat() if s == "MRAT_CLOSED" else None}

    def _h_update_review_status(self, ctx, path, q, b):
        def run():
            m = self._m(b["memberId"])
            prev = m["trc"]["status"]
            if b["targetStatus"] != "SOFT_CLOSED" or prev != "VALIDATION_PASSED":
                raise _err(ErrorCode.PRECONDITION_FAILED, "Transition not allowed from current status.", 422, upstream_code="INVALID_TRANSITION")
            m["trc"]["status"] = "SOFT_CLOSED"
            self._log(m["memberId"], ctx, "SOFT_CLOSED", b.get("reason"))
            return {"memberId": m["memberId"], "previousStatus": prev, "newStatus": "SOFT_CLOSED",
                    "transitionId": f"TRN-{uuid.uuid4().hex[:8]}"}
        return self._idem(ctx, b, run)

    def _h_log_intervention(self, ctx, path, q, b):
        def run():
            m = self._m(path["memberId"])
            m["intervention"]["actions"].append(b["activity"])
            self._log(m["memberId"], ctx, "INTERVENTION_LOGGED", None)
            return {"activityId": f"ACT-{uuid.uuid4().hex[:8]}", "memberId": m["memberId"]}
        return self._idem(ctx, b, run)

    def _h_create_export(self, ctx, path, q, b):
        def run():
            n = len(self._h_get_worklist(ctx, {}, {**(b.get("filters") or {}), "limit": 1000}, {})["items"])
            jid = f"EXP-{uuid.uuid4().hex[:8]}"
            return {"jobId": jid, "format": b["format"], "status": "READY", "rowCount": n,
                    "downloadUrl": f"https://viewer.onprem.guidewell.example/exports/{jid}",
                    "expiresAt": (self.now + timedelta(minutes=15)).isoformat()}
        return self._idem(ctx, b, run)
