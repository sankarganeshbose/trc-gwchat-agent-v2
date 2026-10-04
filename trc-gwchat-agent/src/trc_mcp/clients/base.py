"""The on-prem API abstraction. Tools depend ONLY on `OnPremClient` + `Op`; swapping stub -> real HTTP or changing a
path/method is a config change (see Settings.endpoint_overrides_json), never a tool/agent change.

ALL ROUTES BELOW ARE PLACEHOLDERS / ASSUMPTIONS to be replaced with the real GuideWell API catalogue.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable

from ..security import Principal


class Op(StrEnum):
    # cohort / dashboard
    GET_SUMMARY = "GET_SUMMARY"
    GET_METRICS = "GET_METRICS"
    GET_WORKLIST = "GET_WORKLIST"
    GET_CLOSURE_BOARD = "GET_CLOSURE_BOARD"
    # member
    GET_MEMBER = "GET_MEMBER"
    GET_TRC_STATUS = "GET_TRC_STATUS"
    GET_ADT_EVENTS = "GET_ADT_EVENTS"
    GET_DISCHARGE = "GET_DISCHARGE"
    GET_DISCHARGE_MEDS = "GET_DISCHARGE_MEDS"
    GET_FOLLOWUP = "GET_FOLLOWUP"
    GET_RISK = "GET_RISK"
    GET_INTERVENTION = "GET_INTERVENTION"
    GET_PRIOR_ADMISSIONS = "GET_PRIOR_ADMISSIONS"
    GET_AUDIT = "GET_AUDIT"
    # provider / notifications
    GET_PROVIDER_CONTACTS = "GET_PROVIDER_CONTACTS"
    GET_NOTIFICATION = "GET_NOTIFICATION"
    LIST_NOTIFICATIONS = "LIST_NOTIFICATIONS"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"
    BULK_RESEND_NOTIFICATIONS = "BULK_RESEND_NOTIFICATIONS"
    CREATE_ESCALATION = "CREATE_ESCALATION"
    # validation / closure / records
    GET_VALIDATION = "GET_VALIDATION"
    GET_VALIDATION_SUMMARY = "GET_VALIDATION_SUMMARY"
    RUN_CLAIM_VALIDATION = "RUN_CLAIM_VALIDATION"
    GET_ATTACHMENTS = "GET_ATTACHMENTS"
    CREATE_ATTACHMENT_LINK = "CREATE_ATTACHMENT_LINK"
    GET_MRAT_STATUS = "GET_MRAT_STATUS"
    UPDATE_REVIEW_STATUS = "UPDATE_REVIEW_STATUS"
    LOG_INTERVENTION = "LOG_INTERVENTION"
    CREATE_EXPORT = "CREATE_EXPORT"


# (HTTP method, path template). {placeholders} are filled from `path=`; everything else is query/body.
DEFAULT_ROUTES: dict[Op, tuple[str, str]] = {
    Op.GET_SUMMARY: ("GET", "/api/trc/summary"),
    Op.GET_METRICS: ("GET", "/api/trc/metrics/{dimension}"),
    Op.GET_WORKLIST: ("GET", "/api/trc/worklist"),
    Op.GET_CLOSURE_BOARD: ("GET", "/api/trc/closure-board"),
    Op.GET_MEMBER: ("GET", "/api/trc/members/{memberId}"),
    Op.GET_TRC_STATUS: ("GET", "/api/trc/members/{memberId}/status"),
    Op.GET_ADT_EVENTS: ("GET", "/api/trc/members/{memberId}/adt-events"),
    Op.GET_DISCHARGE: ("GET", "/api/trc/discharges/{memberId}"),
    Op.GET_DISCHARGE_MEDS: ("GET", "/api/trc/discharges/{memberId}/medications"),
    Op.GET_FOLLOWUP: ("GET", "/api/trc/members/{memberId}/followup"),
    Op.GET_RISK: ("GET", "/api/trc/members/{memberId}/risk"),
    Op.GET_INTERVENTION: ("GET", "/api/trc/members/{memberId}/intervention"),
    Op.GET_PRIOR_ADMISSIONS: ("GET", "/api/trc/members/{memberId}/prior-admissions"),
    Op.GET_AUDIT: ("GET", "/api/trc/audit/{memberId}"),
    Op.GET_PROVIDER_CONTACTS: ("GET", "/api/trc/provider/{providerId}"),
    Op.GET_NOTIFICATION: ("GET", "/api/trc/notifications/{memberId}"),
    Op.LIST_NOTIFICATIONS: ("GET", "/api/trc/notifications"),
    Op.SEND_NOTIFICATION: ("POST", "/api/trc/notifications"),
    Op.BULK_RESEND_NOTIFICATIONS: ("POST", "/api/trc/notifications/bulk-resend"),
    Op.CREATE_ESCALATION: ("POST", "/api/trc/escalations"),
    Op.GET_VALIDATION: ("GET", "/api/trc/validation/{memberId}"),
    Op.GET_VALIDATION_SUMMARY: ("GET", "/api/trc/validation-summary"),
    Op.RUN_CLAIM_VALIDATION: ("POST", "/api/trc/validation/claims"),
    Op.GET_ATTACHMENTS: ("GET", "/api/trc/attachments"),
    Op.CREATE_ATTACHMENT_LINK: ("POST", "/api/trc/attachments/{attachmentId}/access-link"),
    Op.GET_MRAT_STATUS: ("GET", "/api/trc/closure/{memberId}"),
    Op.UPDATE_REVIEW_STATUS: ("POST", "/api/trc/closure"),
    Op.LOG_INTERVENTION: ("POST", "/api/trc/interventions/{memberId}/activities"),
    Op.CREATE_EXPORT: ("POST", "/api/trc/exports"),
}


@dataclass(frozen=True)
class CallContext:
    principal: Principal
    request_id: str
    tool: str
    idempotency_key: str | None = None


@runtime_checkable
class OnPremClient(Protocol):
    async def call(
        self,
        op: Op,
        *,
        ctx: CallContext,
        path: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        """Return decoded JSON. Raise `OnPremError` for any failure. Must be safe to call concurrently."""
        ...

    async def aclose(self) -> None: ...
