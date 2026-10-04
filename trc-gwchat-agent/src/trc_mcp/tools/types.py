"""Reusable validated parameter types (the 'input validation' layer of every tool)."""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

# ASSUMPTION: member identifier is the GuideWell HCCID (prototype: HCC-4471829). Loosened to alphanumerics + '-'.
MemberId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9\-]{4,24}$", description="Member HCCID, e.g. HCC-4471829.")]
ProviderId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9\-]{2,24}$", description="Provider Directory id, e.g. PRV-1000.")]
AttachmentId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9\-_]{2,48}$", description="Attachment id from get_attachments.")]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="ISO date YYYY-MM-DD.")]
IdemKey = Annotated[str | None, Field(default=None, min_length=8, max_length=64,
                                      description="Caller-supplied idempotency key. Omit unless instructed by the platform.")]
Reason = Annotated[str, Field(min_length=3, max_length=500, description="Business reason recorded in the audit trail. No PHI beyond ids.")]
Limit = Annotated[int, Field(ge=1, le=50, description="Max rows to return (server also enforces its own cap).")]
