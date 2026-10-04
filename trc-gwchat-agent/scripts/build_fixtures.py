"""Rebuild stub fixtures from the GWChat TRC prototype (MEMBERS array exported to JSON).

Usage: node-export the MEMBERS array to JSON, then
    python scripts/build_fixtures.py /tmp/members_raw.json
The output mirrors the *assumed* on-prem DTO shape (camelCase), NOT the MCP contract shape.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src/trc_mcp/clients/fixtures"
SRC_MAP = {"EIP": "EIP", "Content Central": "CONTENT_CENTRAL", "Provider Vista": "PROVIDER_VISTA", "Claims": "CLAIMS"}
CH_MAP = {"Fax": "FAX", "Email": "EMAIL", "Provider Proxy Task": "PROVIDER_PROXY_TASK"}
TYPE_MAP = {
    "Discharge Summary": "DISCHARGE_SUMMARY", "Progress Note": "PROGRESS_NOTE", "Lab Result": "LAB_RESULT",
    "Imaging Report": "IMAGING_REPORT", "CCDA": "CCDA", "Provider Notification": "PROVIDER_NOTIFICATION",
    "Claim Match": "CLAIM_MATCH",
}


def iso(date: str, time: str | None = None) -> str:
    return f"{date}T{time or '00:00'}:00"


def parse_range(s: str) -> tuple[str, str]:
    a, b = re.split(r"\s*→\s*", s)
    return a.strip(), b.strip()


def convert(raw: dict, providers: dict[str, str], idx: int) -> dict:
    code, _, desc = raw["diagnosis"].partition(" — ")
    pname, _, spec = raw["notification"]["provider"].partition(" — ")
    pid = providers.setdefault(pname, f"PRV-{1000 + len(providers) * 7}")
    n = raw["notification"]
    out = {
        "memberId": raw["hccid"], "uiId": raw["id"], "name": raw["name"], "dob": raw["dob"], "age": raw["age"],
        "gender": raw["gender"], "mrn": raw["mrn"], "lineOfBusiness": raw["lob"].upper(),
        "admitAt": iso(raw["admit"], raw["admitTime"]), "dischargeAt": iso(raw["discharge"], raw["dischargeTime"]),
        "facility": raw["facility"], "facilityType": raw["facilityType"], "admissionType": raw["admissionType"],
        "diagnosis": {"code": code.strip(), "description": desc.strip()},
        "disposition": raw["disposition"],
        "eligibility": {"status": raw["eligibility"], "reason": raw.get("eligibilityReason")},
        "trc": {
            "status": raw["trc"]["status"], "followupDue": raw["trc"]["followupDue"],
            "upload": raw["trc"]["upload"], "claim": raw["trc"]["claim"],
        },
        "risk": raw["risk"],
        "notification": {
            "notificationId": f"NTF-{100200 + idx}", "status": n["status"], "channel": CH_MAP[n["method"]],
            "sentAt": n["sentAt"].replace(" ", "T") + ":00", "ackedAt": (n["ackAt"] or "").replace(" ", "T") + (":00" if n["ackAt"] else "") or None,
            "provider": {"providerId": pid, "name": pname, "specialty": spec}, "response": n["response"],
        },
        "intervention": raw["intervention"],
        "adtEvents": [
            {"type": e["type"], "label": e["label"], "occurredAt": e["when"].replace(" ", "T") + ":00",
             "location": e["loc"], "detail": e["detail"], "rawHl7": e["raw"]} for e in raw["adt"]
        ],
        "priorAdmissions": [],
        "records": [
            {"attachmentId": f"ATT-{raw['id']}-{i + 1}", "name": r["name"], "type": TYPE_MAP[r["type"]],
             "source": SRC_MAP[r["source"]], "date": r["date"], "status": r["status"].upper()}
            for i, r in enumerate(raw["records"])
        ],
        "medications": [{"name": m[0], "dose": m[1], "frequency": m[2], "indication": m[3]} for m in raw["meds"]],
        "followupRecommendations": raw["followups"],
    }
    for p in raw["priorAdmissions"]:
        a, d = parse_range(p["when"])
        pcode, _, pdesc = p["dx"].partition(" ")
        out["priorAdmissions"].append({
            "admitDate": a, "dischargeDate": d, "facility": p["facility"],
            "diagnosis": {"code": pcode, "description": pdesc}, "disposition": p["disp"], "trcOutcome": p["trc"],
        })
    return out


def main(src: str) -> None:
    raw = json.load(open(src))
    providers: dict[str, str] = {}
    members = [convert(m, providers, i) for i, m in enumerate(raw["MEMBERS"])]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "members.json").write_text(json.dumps(members, indent=1))
    print(f"wrote {len(members)} members, {len(providers)} providers")


if __name__ == "__main__":
    main(sys.argv[1])
