"""On-prem DTO -> MCP contract mappers. The ONLY place that knows the on-prem JSON field names.

When the real GuideWell API shapes differ from these assumptions, change this file (and the route table / overrides);
tool signatures, contracts and the agent do not change.
"""
from __future__ import annotations

from typing import Any

from trc_contracts import domain as d
from trc_contracts.common import UploadStatus, ClaimStatus


def _nd(v):
    """Normalize placeholder strings used by source systems for 'no date' (the prototype uses an em dash) to None."""
    return None if v in (None, "", "—", "-", "N/A", "n/a") else v


def _na(v):
    """Source systems send 'N/A' for not-applicable states (excluded members)."""
    return "NOT_APPLICABLE" if v in ("N/A", "n/a") else v


def _dx(x: dict) -> str:
    return f"{x['code']} — {x['description']}"


def summary(r: dict) -> d.TrcSummary:
    return d.TrcSummary(
        measurement_period=r["measurementPeriod"], discharges_identified=r["dischargesIdentified"],
        provider_notified=d.FunnelStage(count=r["providerNotified"]["count"], rate=r["providerNotified"].get("ratePct")),
        validation_passed=d.FunnelStage(count=r["validationPassed"]["count"], rate=r["validationPassed"].get("ratePct")),
        soft_closed=d.FunnelStage(count=r["softClosed"]["count"], rate=r["softClosed"].get("ratePct")),
        mrat_final_closed=r["mratFinalClosed"], no_upload_by_day3=r["noUploadByDay3"],
        no_upload_by_day3_high_risk=r["noUploadByDay3HighRisk"], awaiting_mrat_closure=r["awaitingMratClosure"],
        closure_rate_pct=r["closureRatePct"], prior_quarter_closure_rate_pct=r.get("priorQuarterClosureRatePct"),
        plan_target_pct=r.get("planTargetPct"), active_window_members=r["activeWindowMembers"],
        risk_tiers=[d.RiskTierCount(tier=t["tier"], count=t["count"], note=t.get("note")) for t in r["riskTiers"]],
    )


def metrics(r: dict) -> d.MetricBreakdown:
    return d.MetricBreakdown(
        dimension=r["dimension"], measurement_period=r["measurementPeriod"],
        points=[d.MetricPoint(label=p["label"], denominator=p.get("denominator"), value=p["value"],
                              unit=r.get("unit", "percent")) for p in r["points"]])


def _worklist_item(i: dict) -> d.WorklistItem:
    return d.WorklistItem(
        member_id=i["memberId"], member_name=i["name"], line_of_business=i.get("lineOfBusiness"),
        admit_date=i["admitAt"][:10], discharge_date=i["dischargeAt"][:10], facility=i["facility"],
        diagnosis=_dx(i["diagnosis"]), disposition=i["disposition"], eligibility=i["eligibility"],
        trc_status=i["trcStatus"], risk_score=i.get("riskScore"), risk_tier=i.get("riskTier"),
        notification_status=i.get("notificationStatus"), notification_channel=i.get("notificationChannel"),
        provider_upload_status=_na(i["uploadStatus"]), followup_due=_nd(i.get("followupDue")),
        days_since_discharge=i["daysSinceDischarge"], past_day3_no_upload=i["pastDay3NoUpload"])


def worklist(r: dict, *, sort: str, filters: dict) -> d.WorklistPage:
    items = [_worklist_item(i) for i in r["items"]]
    return d.WorklistPage(items=items, returned=len(items), total_matching=r["total"], sort=sort,
                          applied_filters=filters, next_cursor=r.get("nextCursor"))


def closure_board(r: dict) -> d.ClosureBoard:
    return d.ClosureBoard(columns=[
        d.ClosureColumn(status=c["status"], label=c["label"], count=c["count"], cards=[
            d.ClosureCard(member_id=k["memberId"], member_name=k["name"], risk_tier=k.get("riskTier"),
                          trc_status=k["trcStatus"], tag=k["tag"], followup_due=_nd(k.get("followupDue"))) for k in c["cards"]])
        for c in r["columns"]])


def member(r: dict) -> d.MemberDetails:
    return d.MemberDetails(
        member_id=r["memberId"], name=r["name"], dob=r["dob"], age=r["age"], gender=r["gender"], mrn=r["mrn"],
        line_of_business=r.get("lineOfBusiness"), admit_at=r["admitAt"], discharge_at=r["dischargeAt"],
        facility=r["facility"], facility_type=r["facilityType"], admission_type=r["admissionType"],
        diagnosis_code=r["diagnosis"]["code"], diagnosis_description=r["diagnosis"]["description"],
        disposition=r["disposition"], eligibility=r["eligibility"]["status"],
        ineligibility_reason=r["eligibility"].get("reason"), trc_status=r["trcStatus"], followup_due=_nd(r.get("followupDue")))


def trc_status(r: dict) -> d.MemberTrcStatus:
    return d.MemberTrcStatus(
        member_id=r["memberId"], trc_status=r["status"], eligibility=r["eligibility"]["status"],
        ineligibility_reason=r["eligibility"].get("reason"), followup_due=_nd(r.get("followupDue")),
        steps=[d.TrcStep(key=x["key"], label=x["label"], state=x["state"], detail=x["detail"]) for x in r["steps"]])


def adt(r: dict) -> d.AdtTimeline:
    return d.AdtTimeline(member_id=r["memberId"], events=[
        d.AdtEvent(event_type=e["type"], label=e["label"], occurred_at=e["occurredAt"], location=e["location"],
                   detail=e["detail"], raw_hl7=e.get("rawHl7")) for e in r["events"]])


def discharge(r: dict) -> d.DischargeSummary:
    return d.DischargeSummary(member_id=r["memberId"], diagnosis_code=r["diagnosis"]["code"],
                              diagnosis_description=r["diagnosis"]["description"], disposition=r["disposition"],
                              facility=r["facility"], source_documents=r["sourceDocuments"], last_updated=r["lastUpdated"])


def discharge_meds(r: dict) -> d.DischargeMedications:
    meds = [d.DischargeMedication(name=m["name"], dose=m["dose"], frequency=m["frequency"], indication=m["indication"])
            for m in r["medications"]]
    return d.DischargeMedications(member_id=r["memberId"], medications=meds, on_file=bool(meds))


def followup(r: dict) -> d.FollowupStatus:
    days = r.get("daysUntilDue")
    return d.FollowupStatus(member_id=r["memberId"], followup_due=_nd(r.get("followupDue")), days_until_due=days,
                            overdue=days is not None and days < 0, recommendations=r["recommendations"],
                            pcp_visit_confirmed=r.get("pcpVisitConfirmed"))


def risk(r: dict) -> d.RiskAssessment:
    return d.RiskAssessment(member_id=r["memberId"], score=r["score"], tier=r["tier"], factors=r["factors"])


def intervention(r: dict) -> d.InterventionStatus:
    return d.InterventionStatus(member_id=r["memberId"], status=r.get("status"), coordinator=_nd(r.get("coordinator")),
                                due_date=_nd(r.get("dueDate")),
                                activities=[d.InterventionActivity(description=a) for a in r.get("actions", [])])


def prior(r: dict) -> d.PriorAdmissions:
    return d.PriorAdmissions(member_id=r["memberId"], admissions=[
        d.PriorAdmission(admit_date=a["admitDate"], discharge_date=a["dischargeDate"], facility=a["facility"],
                         diagnosis=_dx(a["diagnosis"]), disposition=a["disposition"], trc_outcome=a["trcOutcome"])
        for a in r["admissions"]])


def _audit(e: dict) -> d.AuditEntry:
    return d.AuditEntry(at=e["at"], actor=e["actor"], action=e["action"], detail=e.get("detail"))


def audit(r: dict) -> d.AuditEvents:
    return d.AuditEvents(member_id=r["memberId"], events=[_audit(e) for e in r["events"]])


def provider_contacts(r: dict) -> d.ProviderContacts:
    return d.ProviderContacts(provider_id=r["providerId"], provider_name=r["name"], specialty=r.get("specialty"), contacts=[
        d.ProviderContact(channel=c["channel"], value=c.get("value"), verified=c["verified"],
                          verified_on=c.get("verifiedOn"), preferred=c.get("preferred", False)) for c in r["contacts"]])


def outreach(r: dict) -> d.ProviderOutreach:
    p = r.get("provider") or {}
    return d.ProviderOutreach(
        member_id=r["memberId"], notification_id=r.get("notificationId"), provider_id=p.get("providerId"),
        provider_name=p.get("name"), event=r.get("event", "Discharge (A03)"), status=r.get("status"),
        channel=r.get("channel"), sent_at=r.get("sentAt"), acknowledged_at=r.get("ackedAt"),
        provider_response=r.get("response"), vista_upload=_na(r["uploadStatus"]), vista_upload_date=_nd(r.get("uploadDate")),
        alert_fields=r.get("alertFields", []), proxy_task_updated=r.get("proxyTaskUpdated"),
        audit_trail=[_audit(e) for e in r.get("auditTrail", [])])


def outreach_list(r: dict, *, filters: dict) -> d.OutreachPage:
    items = []
    for i in r["items"]:
        p = i.get("provider") or {}
        items.append(d.OutreachListItem(
            member_id=i["memberId"], member_name=i["memberName"], event=i.get("event", "Discharge (A03)"),
            provider_id=p.get("providerId"), provider_name=p.get("name"), facility=i["facility"],
            channel=i.get("channel"), sent_at=i.get("sentAt"), status=i.get("status"),
            provider_response=i.get("response"), vista_upload=_na(i["uploadStatus"]),
            resend_allowed=i.get("status") in ("FAILED", "PENDING")))
    return d.OutreachPage(items=items, returned=len(items), total_matching=r["total"], applied_filters=filters)


def send_result(r: dict) -> d.NotificationSendResult:
    return d.NotificationSendResult(notification_id=r["notificationId"], member_id=r["memberId"], status=r["status"],
                                    channel=r["channel"], proxy_task_updated=r["proxyTaskUpdated"],
                                    idempotent_replay=r.get("idempotentReplay", False))


def bulk_result(r: dict) -> d.BulkResendResult:
    return d.BulkResendResult(batch_id=r["batchId"], requested=r["requested"],
                              accepted=[send_result(a) for a in r["accepted"]],
                              skipped=[d.BulkSkip(member_id=s["memberId"], reason=s["reason"]) for s in r["skipped"]])


def escalation(r: dict) -> d.EscalationResult:
    return d.EscalationResult(escalation_id=r["escalationId"], member_id=r["memberId"],
                              notification_id=r.get("notificationId"), escalated_to=r.get("escalatedTo"),
                              idempotent_replay=r.get("idempotentReplay", False))


def validation_evidence(r: dict) -> d.ValidationEvidence:
    return d.ValidationEvidence(
        member_id=r["memberId"], window_days=r["windowDays"], upload_status=UploadStatus(_na(r["upload"]["status"])),
        upload_date=_nd(r["upload"].get("date")), claim_status=ClaimStatus(_na(r["claim"]["status"])), claim_date=_nd(r["claim"].get("date")),
        care_navi_task_status=r.get("careNaviTaskStatus"), rule_outcome=r["ruleOutcome"],
        items=[d.EvidenceItem(name=i["name"], source_system=i["sourceSystem"], available=i["available"], detail=i.get("detail"))
               for i in r["items"]])


def validation_run(r: dict) -> d.ValidationRun:
    res = [d.ValidationResult(member_id=x["memberId"], outcome=x["outcome"], reasons=x["reasons"], checked_at=x["checkedAt"],
                              eligible_for_soft_closure=x.get("eligibleForSoftClosure", False)) for x in r["results"]]
    return d.ValidationRun(run_id=r["runId"], results=res, evaluated=len(res),
                           passed=sum(x.outcome == "PASSED" for x in res), failed=sum(x.outcome == "FAILED" for x in res),
                           persisted=r["persisted"])


def validation_summary(r: dict) -> d.ValidationSummary:
    return d.ValidationSummary(
        window_days=r["windowDays"], evaluated_last_90_days=r["evaluatedLast90Days"],
        notified_within_1_day_pct=r["notifiedWithin1DayPct"], records_uploaded_by_day3_pct=r["uploadedByDay3Pct"],
        claims_validated_pct=r["claimsValidatedPct"], passed_soft_closed_pct=r["passedSoftClosedPct"],
        failed_pct=r["failedPct"], avg_days_discharge_to_soft_close=r["avgDaysToSoftClose"],
        awaiting_mrat_final_closure=r["awaitingMratFinalClosure"])


def attachments(r: dict, *, filters: dict) -> d.AttachmentList:
    items = [d.Attachment(attachment_id=a["attachmentId"], member_id=a["memberId"], member_name=a.get("memberName"),
                          name=a["name"], record_type=a["type"], source=a["source"], date=a["date"], status=a["status"])
             for a in r["items"]]
    return d.AttachmentList(items=items, returned=len(items), applied_filters=filters)


def attachment_link(r: dict) -> d.AttachmentAccessLink:
    return d.AttachmentAccessLink(attachment_id=r["attachmentId"], url=r["url"], expires_at=r["expiresAt"])


def mrat(r: dict) -> d.MratReviewStatus:
    return d.MratReviewStatus(member_id=r["memberId"], trc_status=r["trcStatus"],
                              awaiting_final_closure=r["awaitingFinalClosure"], assigned_nurse=r.get("assignedNurse"),
                              mrat_deeplink=r.get("mratDeeplink"), closed_at=r.get("closedAt"))


def review_result(r: dict, *, target: Any) -> d.ReviewStatusResult:
    return d.ReviewStatusResult(member_id=r["memberId"], previous_status=r["previousStatus"], new_status=r["newStatus"],
                                transition_id=r["transitionId"], requested_target=target,
                                idempotent_replay=r.get("idempotentReplay", False))


def intervention_log(r: dict) -> d.InterventionLogResult:
    return d.InterventionLogResult(activity_id=r["activityId"], member_id=r["memberId"],
                                   idempotent_replay=r.get("idempotentReplay", False))


def export_job(r: dict) -> d.ExportJob:
    return d.ExportJob(job_id=r["jobId"], format=r["format"], status=r["status"], row_count=r.get("rowCount"),
                       download_url=r.get("downloadUrl"), expires_at=r.get("expiresAt"))
