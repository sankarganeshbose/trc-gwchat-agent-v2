"""Per-turn evidence ledger. Everything the user sees as 'data' is built from here — never from LLM text."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..models.schemas import PendingAction
from ..policy import canonical


@dataclass
class ToolRecord:
    tool: str
    args: dict[str, Any]
    ok: bool
    data: dict | None
    error: dict | None
    meta: dict
    origin: str  # llm | plan | executor
    section: str | None = None
    duration_ms: int | None = None
    intent: str | None = None  # set by composite plans so one user request maps to one intent


@dataclass
class ToolLedger:
    records: list[ToolRecord] = field(default_factory=list)
    pending: list[PendingAction] = field(default_factory=list)
    blocked: list[tuple[str, str]] = field(default_factory=list)
    calls: int = 0

    def add(self, rec: ToolRecord) -> None:
        self.records.append(rec)

    def ok_records(self, tool: str) -> list[ToolRecord]:
        return [r for r in self.records if r.tool == tool and r.ok]

    def failures(self) -> list[ToolRecord]:
        return [r for r in self.records if not r.ok]

    def evidence_text(self) -> str:
        """Everything the narrative may legitimately reference (used by the grounding check)."""
        return json.dumps([r.data for r in self.records if r.ok], default=str)


def failure_envelope(code: str, message: str, retryable: bool = False) -> dict:
    return {"ok": False, "data": None, "error": {"code": code, "message": message, "retryable": retryable}, "meta": {}}


def parse_tool_result(result: dict) -> dict:
    """Normalize a Strands/MCP tool result into the contract Envelope dict. Fails CLOSED on anything unexpected."""
    sc = result.get("structuredContent")
    if isinstance(sc, dict) and "ok" in sc and "meta" in sc:
        return sc
    for item in result.get("content") or []:
        txt = item.get("text") if isinstance(item, dict) else None
        if txt:
            try:
                obj = json.loads(txt)
                if isinstance(obj, dict) and "ok" in obj and "meta" in obj:
                    return obj
            except ValueError:
                pass
    if result.get("status") == "error" or result.get("isError"):
        # MCP-level error (e.g., argument validation). Do not forward raw text.
        return failure_envelope("INVALID_ARGUMENT", "Tool rejected the request arguments.")
    return failure_envelope("UPSTREAM_SCHEMA_MISMATCH", "Tool result was not in the expected envelope format.")


def record_from_envelope(tool: str, args: dict, env: dict, *, origin: str, section: str | None = None, intent: str | None = None) -> ToolRecord:
    return ToolRecord(tool=canonical(tool), args=args, ok=bool(env.get("ok")), data=env.get("data"), error=env.get("error"),
                      meta=env.get("meta") or {}, origin=origin, section=section, duration_ms=(env.get("meta") or {}).get("latency_ms"), intent=intent)
