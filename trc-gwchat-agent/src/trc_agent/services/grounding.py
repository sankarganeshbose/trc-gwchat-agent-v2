"""Post-generation grounding check for the ONE LLM-authored field (`message`). Fails closed to a deterministic summary."""
from __future__ import annotations

import json
import re

from .ledger import ToolLedger

ID_RE = re.compile(r"\b(?:HCC|PRV|NTF|ESC|TRN|ACT|EXP|VAL|BLK|ATT)-[A-Za-z0-9\-]+\b")
COMPLETED_CLAIM_RE = re.compile(
    r"\b(has|have|was|were|been)\s+(successfully\s+)?(sent|resent|re-sent|escalated|soft[- ]closed|closed|logged|exported)\b|"
    r"\bI(?:'ve| have)?\s+(sent|resent|escalated|soft[- ]closed|closed|logged|exported)\b", re.I)


def check_narrative(message: str, ledger: ToolLedger, user_text: str) -> list[str]:
    """Return a list of violations (empty => grounded)."""
    problems: list[str] = []
    evidence = ledger.evidence_text() + " " + user_text + " " + json.dumps([p.arguments for p in ledger.pending], default=str)  # queued-action args are legitimate references
    for ident in set(ID_RE.findall(message)):
        if ident not in evidence:
            problems.append(f"UNGROUNDED_IDENTIFIER:{ident}")
    executed = any(r.origin == "executor" and r.ok for r in ledger.records)
    if COMPLETED_CLAIM_RE.search(message) and not executed:
        # Allowed only when describing a queued action ("awaiting confirmation") — otherwise it's an unsupported completion claim
        if not re.search(r"await|pending|confirm|queued|not been", message, re.I):
            problems.append("UNSUPPORTED_COMPLETION_CLAIM")
    return problems
