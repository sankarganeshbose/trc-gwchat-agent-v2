"""GWChat <-> agent contract. Everything GWChat renders comes from `blocks` (deterministic, tool-sourced);
`message` is the only LLM-authored field and is grounding-checked."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..policy import MEMBER_ID_RE


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ───────────────────────── request ─────────────────────────
class GWChatContext(_M):
    """UI state GWChat passes explicitly. The agent keeps NO conversational memory of clinical facts."""

    selected_member_id: str | None = Field(None, description="Member card currently open in GWChat; resolves 'this member'.")
    active_filters: dict[str, str | int | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self):
        if self.selected_member_id and not MEMBER_ID_RE.match(self.selected_member_id):
            raise ValueError("selected_member_id has an invalid format")
        return self


class Confirmation(_M):
    ticket: str = Field(min_length=20, max_length=4000)
    decision: Literal["approve", "reject"]


class GWChatRequest(_M):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str = Field(min_length=8, max_length=128)
    user_id: str = Field(min_length=1, max_length=128, description="Authenticated GWChat user (from the validated JWT, not the payload, in production).")
    message: str | None = Field(None, max_length=4000)
    context: GWChatContext = Field(default_factory=GWChatContext)
    confirmation: Confirmation | None = None

    @model_validator(mode="after")
    def _one_of(self):
        if bool(self.message and self.message.strip()) == bool(self.confirmation):
            raise ValueError("Provide exactly one of `message` or `confirmation`.")
        return self


# ───────────────────────── response ─────────────────────────
class BlockType(StrEnum):
    KPI_SUMMARY = "KPI_SUMMARY"
    METRIC_BREAKDOWN = "METRIC_BREAKDOWN"
    WORKLIST = "WORKLIST"
    CLOSURE_BOARD = "CLOSURE_BOARD"
    MEMBER_RECORD = "MEMBER_RECORD"
    MEMBER_SECTION = "MEMBER_SECTION"
    NOTIFICATIONS = "NOTIFICATIONS"
    VALIDATION_RUN = "VALIDATION_RUN"
    VALIDATION_SUMMARY = "VALIDATION_SUMMARY"
    RECORDS = "RECORDS"
    RECORD_LINK = "RECORD_LINK"
    PROVIDER_CONTACTS = "PROVIDER_CONTACTS"
    MRAT_STATUS = "MRAT_STATUS"
    ACTION_RESULT = "ACTION_RESULT"


class Block(_M):
    type: BlockType
    title: str
    section: str | None = None
    source_tools: list[str]
    source_systems: list[str] = Field(default_factory=list)
    as_of: datetime | None = None
    data: dict[str, Any] = Field(description="Verbatim tool `data` (trc_contracts.domain models). Never LLM-generated.")


class DataGap(_M):
    tool: str
    section: str | None = None
    code: str
    message: str
    retryable: bool = False


class PendingAction(_M):
    ticket: str
    tool: str
    summary: str
    arguments: dict[str, Any]
    expires_at: datetime


class ToolTrace(_M):
    tool: str
    ok: bool
    outcome: str
    latency_ms: int | None = None
    error_code: str | None = None
    request_id: str | None = None


class ResponseStatus(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"  # some requested data unavailable -> see data_gaps
    UNAVAILABLE = "UNAVAILABLE"  # nothing could be retrieved
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    NARRATIVE_ONLY = "NARRATIVE_ONLY"  # no tool used (clarification, out-of-scope refusal, capability question)
    ERROR = "ERROR"


class GWChatResponse(_M):
    request_id: str
    session_id: str
    intent: str
    status: ResponseStatus
    message: str
    blocks: list[Block] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    pending_actions: list[PendingAction] = Field(default_factory=list)
    tool_trace: list[ToolTrace] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
