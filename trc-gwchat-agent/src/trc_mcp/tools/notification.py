"""Provider notification reads and writes (Notification Processor)."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from trc_contracts import domain as d
from trc_contracts.common import Channel, Envelope, ErrorCode, NotificationStatus, ProviderResponse

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ..errors import OnPremError
from ..security import READ as S_READ, WRITE as S_WRITE
from ._common import READ, WRITE
from .types import IdemKey, MemberId, Reason


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_provider_outreach", annotations=READ, tags={"trc", "read", "notification"})
    async def get_provider_outreach(member_id: MemberId) -> Envelope[d.ProviderOutreach]:
        """Provider notification status for ONE member: provider, channel, sent/ack times, provider response, Provider Vista
        upload status, alert content fields, whether the Proxy Task was updated, and the audit trail."""
        return await run_tool(tc, tool="get_provider_outreach", source="Notification Processor / Provider Vista", op=Op.GET_NOTIFICATION,
                              path={"memberId": member_id}, model=d.ProviderOutreach, mapper=mappers.outreach, log_refs={"member": member_id})

    @mcp.tool(name="list_provider_outreach", annotations=READ, tags={"trc", "read", "notification"})
    async def list_provider_outreach(
        status: NotificationStatus | None = None,
        channel: Channel | None = None,
        facility: Annotated[str | None, Field(max_length=120)] = None,
        provider_response: ProviderResponse | None = None,
        unacknowledged_only: Annotated[bool, Field(description="Everything not yet ACKNOWLEDGED")] = False,
        limit: Annotated[int, Field(ge=1, le=50)] = 25,
    ) -> Envelope[d.OutreachPage]:
        """Cohort view of TRC provider notifications (admission A01 / discharge A03 alerts) with filters. Use for 'which providers have not
        acknowledged their TRC discharge notifications?' (unacknowledged_only=true). Each row has `resend_allowed`."""
        limit = min(limit, tc.settings.max_page_size)
        applied = {k: (v.value if hasattr(v, "value") else v) for k, v in {
            "status": status, "channel": channel, "facility": facility, "provider_response": provider_response,
            "unacknowledged_only": unacknowledged_only or None, "limit": limit}.items() if v is not None}
        q = {"status": status, "channel": channel, "facility": facility, "response": provider_response,
             "unacknowledged": True if unacknowledged_only else None, "limit": limit}
        q = {k: (v.value if hasattr(v, "value") else v) for k, v in q.items() if v is not None}
        return await run_tool(tc, tool="list_provider_outreach", source="Notification Processor", op=Op.LIST_NOTIFICATIONS, query=q,
                              model=d.OutreachPage, mapper=lambda r: mappers.outreach_list(r, filters=applied))

    @mcp.tool(name="send_provider_notification", annotations=WRITE, tags={"trc", "write", "notification"})
    async def send_provider_notification(
        member_id: MemberId,
        reason: Reason,
        channel: Annotated[Channel | None, Field(description="Override channel. Must be a VERIFIED contact (see get_provider_contacts). Default: original channel.")] = None,
        idempotency_key: IdemKey = None,
    ) -> Envelope[d.NotificationSendResult]:
        """WRITE. Resend ONE standardized TRC provider alert for a member whose alert is FAILED or PENDING. On-prem enforces that
        other statuses are rejected (PRECONDITION_FAILED) and updates the Proxy Task after sending. Requires explicit user
        confirmation (enforced by the agent)."""
        body = {"memberId": member_id, "channel": channel.value if channel else None, "reason": reason}
        return await run_tool(tc, tool="send_provider_notification", source="Notification Processor", op=Op.SEND_NOTIFICATION,
                              scopes=(S_READ, S_WRITE), body=body, write=True, idempotency_key=idempotency_key,
                              model=d.NotificationSendResult, mapper=mappers.send_result, log_refs={"member": member_id})

    @mcp.tool(name="resend_notifications_bulk", annotations=WRITE, tags={"trc", "write", "notification"})
    async def resend_notifications_bulk(
        member_ids: Annotated[list[MemberId], Field(min_length=1, max_length=25, description="Explicit list. No implicit 'all' scope.")],
        reason: Reason,
        idempotency_key: IdemKey = None,
    ) -> Envelope[d.BulkResendResult]:
        """WRITE. Resend alerts for an EXPLICIT list of members (UI: 'Bulk Resend to Non-Responsive'). Compose the list from
        list_provider_outreach first and show it to the user. Per-member rule failures are returned in `skipped`, not raised.
        Requires explicit user confirmation (enforced by the agent)."""
        ids = list(dict.fromkeys(member_ids))

        def precheck() -> None:
            if len(ids) > tc.settings.max_bulk_resend:
                raise OnPremError(ErrorCode.INVALID_ARGUMENT, f"At most {tc.settings.max_bulk_resend} members per bulk resend.")

        return await run_tool(tc, tool="resend_notifications_bulk", source="Notification Processor", op=Op.BULK_RESEND_NOTIFICATIONS,
                              scopes=(S_READ, S_WRITE), body={"memberIds": ids, "reason": reason}, write=True, idempotency_key=idempotency_key,
                              precheck=precheck, model=d.BulkResendResult, mapper=mappers.bulk_result)

    @mcp.tool(name="escalate_to_provider_manager", annotations=WRITE, tags={"trc", "write", "notification"})
    async def escalate_to_provider_manager(
        member_id: MemberId, reason: Reason, idempotency_key: IdemKey = None,
    ) -> Envelope[d.EscalationResult]:
        """WRITE. Escalate a member's non-responsive/failed provider notification to the facility's Provider Manager.
        Requires explicit user confirmation (enforced by the agent)."""
        return await run_tool(tc, tool="escalate_to_provider_manager", source="Notification Processor", op=Op.CREATE_ESCALATION,
                              scopes=(S_READ, S_WRITE), body={"memberId": member_id, "reason": reason}, write=True,
                              idempotency_key=idempotency_key, model=d.EscalationResult, mapper=mappers.escalation,
                              log_refs={"member": member_id})
