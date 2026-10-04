"""Exception taxonomy. Clients raise OnPremError; the tool wrapper converts to the Envelope error model."""
from __future__ import annotations

from trc_contracts.common import ErrorCode, ToolFailure


class OnPremError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False,
                 upstream_status: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.upstream_status = upstream_status
        self.details = details or {}

    def to_failure(self) -> ToolFailure:
        return ToolFailure(code=self.code, message=self.message, retryable=self.retryable,
                           upstream_status=self.upstream_status, details=self.details)


def from_status(status: int, *, body_code: str | None = None) -> OnPremError:
    """Map an upstream HTTP status to the contract error model. Upstream bodies are never forwarded."""
    if status == 400 or status == 422:
        return OnPremError(ErrorCode.INVALID_ARGUMENT if status == 400 else ErrorCode.PRECONDITION_FAILED,
                           "Upstream rejected the request.", upstream_status=status, details={"upstream_code": body_code})
    if status == 401:
        return OnPremError(ErrorCode.UNAUTHENTICATED, "Upstream authentication failed.", upstream_status=status)
    if status == 403:
        return OnPremError(ErrorCode.FORBIDDEN, "Not permitted to access this resource.", upstream_status=status)
    if status == 404:
        return OnPremError(ErrorCode.NOT_FOUND, "Requested record was not found.", upstream_status=status)
    if status == 409:
        return OnPremError(ErrorCode.CONFLICT, "Conflicting request (idempotency or state).", upstream_status=status)
    if status == 429:
        return OnPremError(ErrorCode.RATE_LIMITED, "Upstream rate limit reached.", retryable=True, upstream_status=status)
    if status in (502, 503, 504):
        return OnPremError(ErrorCode.UPSTREAM_UNAVAILABLE, "Upstream system is unavailable.", retryable=True, upstream_status=status)
    return OnPremError(ErrorCode.UPSTREAM_ERROR, "Upstream system error.", retryable=status >= 500, upstream_status=status)
