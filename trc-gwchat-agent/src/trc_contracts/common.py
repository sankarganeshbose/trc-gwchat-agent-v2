"""Envelope, error model and enums shared by every MCP tool."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Contract(BaseModel):
    """Base for all contract models: immutable-ish, no silent extras on the way *out*."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# ───────────────────────────── errors ─────────────────────────────
class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"  # e.g. idempotency key reuse with different payload
    PRECONDITION_FAILED = "PRECONDITION_FAILED"  # business rule (e.g. soft-close before validation passed)
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    UPSTREAM_SCHEMA_MISMATCH = "UPSTREAM_SCHEMA_MISMATCH"
    INTERNAL = "INTERNAL"


class ToolFailure(Contract):
    code: ErrorCode
    message: str = Field(description="Safe, PHI-free message. Never contains stack traces or upstream bodies.")
    retryable: bool = False
    upstream_status: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Meta(Contract):
    request_id: str
    tool: str
    source_system: str = Field(description="Logical enterprise system that owns the data, e.g. 'CareNavi'.")
    as_of: datetime
    latency_ms: int
    idempotency_key: str | None = None
    read_only: bool = True


class Envelope(Contract, Generic[T]):
    """Every tool returns this. `ok=False` => `error` is set and `data` is None (never partial)."""

    ok: bool
    data: T | None = None
    error: ToolFailure | None = None
    meta: Meta


# ───────────────────────────── enums ─────────────────────────────
class TrcStatus(StrEnum):
    DISCHARGE_IDENTIFIED = "DISCHARGE_IDENTIFIED"
    PROVIDER_NOTIFIED = "PROVIDER_NOTIFIED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    SOFT_CLOSED = "SOFT_CLOSED"
    MRAT_CLOSED = "MRAT_CLOSED"
    EXCLUDED = "EXCLUDED"


class RiskTier(StrEnum):
    HIGH = "HIGH"  # > 20% readmission risk (prototype tiering)
    MEDIUM = "MEDIUM"  # 10-20%
    LOW = "LOW"  # < 10%


class Eligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class Disposition(StrEnum):
    HOME = "HOME"
    HOME_WITH_SERVICES = "HOME_WITH_SERVICES"
    TRANSFERRED_TO_SNF = "TRANSFERRED_TO_SNF"
    TRANSFERRED_TO_REHAB = "TRANSFERRED_TO_REHAB"
    TRANSFERRED_ACUTE = "TRANSFERRED_ACUTE"
    HOSPICE = "HOSPICE"
    EXPIRED = "EXPIRED"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"


class Channel(StrEnum):
    FAX = "FAX"
    EMAIL = "EMAIL"
    PROVIDER_PROXY_TASK = "PROVIDER_PROXY_TASK"


class ProviderResponse(StrEnum):
    PENDING_RESPONSE = "PENDING_RESPONSE"
    NON_RESPONSIVE = "NON_RESPONSIVE"
    APPOINTMENT_SCHEDULED = "APPOINTMENT_SCHEDULED"
    APPOINTMENT_CONFIRMED = "APPOINTMENT_CONFIRMED"


class UploadStatus(StrEnum):
    UPLOADED = "UPLOADED"
    NOT_UPLOADED = "NOT_UPLOADED"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # e.g. member excluded from TRC


class ClaimStatus(StrEnum):
    MATCHED = "MATCHED"
    PENDING = "PENDING"
    NOT_FOUND = "NOT_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class InterventionState(StrEnum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class RecordSource(StrEnum):
    PROVIDER_VISTA = "PROVIDER_VISTA"
    EIP = "EIP"
    CONTENT_CENTRAL = "CONTENT_CENTRAL"
    CLAIMS = "CLAIMS"


class RecordType(StrEnum):
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    PROGRESS_NOTE = "PROGRESS_NOTE"
    LAB_RESULT = "LAB_RESULT"
    IMAGING_REPORT = "IMAGING_REPORT"
    CCDA = "CCDA"
    PROVIDER_NOTIFICATION = "PROVIDER_NOTIFICATION"
    CLAIM_MATCH = "CLAIM_MATCH"


class LineOfBusiness(StrEnum):
    MEDICARE = "MEDICARE"
    COMMERCIAL = "COMMERCIAL"
    MEDICAID = "MEDICAID"


class MetricDimension(StrEnum):
    COMPONENT = "COMPONENT"  # TRC measure components compliance
    FACILITY = "FACILITY"  # open gaps by facility
    DISPOSITION = "DISPOSITION"  # discharge disposition breakdown
    TREND = "TREND"  # trailing-12-month closure rate


class ReviewStatusTarget(StrEnum):
    """Targets the *agent* may request. MRAT_CLOSED is intentionally absent: final closure is human-only (HEDIS nurse).
    ASSUMPTION: soft closure also places the task in the MRAT review queue (prototype: 'Soft Closed / MRAT')."""

    SOFT_CLOSED = "SOFT_CLOSED"


class ExportFormat(StrEnum):
    CSV = "CSV"
    PDF = "PDF"
