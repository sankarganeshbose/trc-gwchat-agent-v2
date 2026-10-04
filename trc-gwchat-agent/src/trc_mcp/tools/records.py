"""Medical-record attachment access. Metadata + short-lived on-prem viewer links only; bytes never transit AWS."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from trc_contracts import domain as d
from trc_contracts.common import Envelope, RecordSource, RecordType

from ..adapters import mappers
from ..clients.base import Op
from ..deps import ToolContext, run_tool
from ..security import READ as S_READ, RECORDS as S_RECORDS
from ._common import COMPUTE, READ
from .types import AttachmentId, MemberId


def register(mcp: FastMCP, tc: ToolContext) -> None:
    @mcp.tool(name="get_attachments", annotations=READ, tags={"trc", "read", "records"})
    async def get_attachments(
        member_id: MemberId | None = None,
        record_type: RecordType | None = None,
        source: RecordSource | None = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 25,
    ) -> Envelope[d.AttachmentList]:
        """List TRC medical records/attachments (discharge summaries, CCDAs, progress notes, labs, imaging, provider notifications, claim matches)
        from Provider Vista / Link, EIP, Content Central and Claims. READ-ONLY metadata; every access is audit-logged on-prem
        (requires scope trc.records.read). Omit member_id to list across the worklist."""
        limit = min(limit, tc.settings.max_page_size)
        applied = {k: (v.value if hasattr(v, "value") else v) for k, v in {"member_id": member_id, "record_type": record_type, "source": source, "limit": limit}.items() if v is not None}
        q = {"memberId": member_id, "recordType": record_type.value if record_type else None, "source": source.value if source else None, "limit": limit}
        return await run_tool(tc, tool="get_attachments", source="Provider Vista / EIP / Content Central", op=Op.GET_ATTACHMENTS,
                              scopes=(S_READ, S_RECORDS), query=q, model=d.AttachmentList,
                              mapper=lambda r: mappers.attachments(r, filters=applied), log_refs={"member": member_id})

    @mcp.tool(name="get_attachment_access_link", annotations=COMPUTE, tags={"trc", "compute", "records"})
    async def get_attachment_access_link(attachment_id: AttachmentId) -> Envelope[d.AttachmentAccessLink]:
        """Get a short-lived, read-only, audit-logged on-prem viewer URL for ONE attachment (UI 'View'). Document content is never returned by MCP."""
        return await run_tool(tc, tool="get_attachment_access_link", source="EIP / Content Central", op=Op.CREATE_ATTACHMENT_LINK,
                              scopes=(S_READ, S_RECORDS), path={"attachmentId": attachment_id}, compute=True,
                              model=d.AttachmentAccessLink, mapper=mappers.attachment_link)
