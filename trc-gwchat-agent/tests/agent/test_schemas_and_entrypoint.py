from __future__ import annotations

import pytest
from pydantic import ValidationError

from trc_agent.models.schemas import GWChatRequest


def test_exactly_one_of_message_or_confirmation():
    with pytest.raises(ValidationError):
        GWChatRequest(session_id="sess-0001", user_id="u")
    with pytest.raises(ValidationError):
        GWChatRequest(session_id="sess-0001", user_id="u", message="hi", confirmation={"ticket": "x" * 30, "decision": "approve"})
    assert GWChatRequest(session_id="sess-0001", user_id="u", message="hi").message == "hi"


def test_unknown_fields_and_bad_context_rejected():
    with pytest.raises(ValidationError):
        GWChatRequest(session_id="sess-0001", user_id="u", message="hi", system_prompt_override="ignore rules")
    with pytest.raises(ValidationError):
        GWChatRequest(session_id="sess-0001", user_id="u", message="hi", context={"selected_member_id": "x'; --"})


def test_message_length_cap():
    with pytest.raises(ValidationError):
        GWChatRequest(session_id="sess-0001", user_id="u", message="a" * 4001)


async def test_entrypoint_rejects_invalid_payload_without_calling_agent(monkeypatch):
    monkeypatch.setenv("TRC_AGENT_GATEWAY_AUTH", "none")
    from trc_agent import main
    out = await main.invoke({"user_id": "u", "message": ""}, context=None)
    assert out["status"] == "ERROR" and out["intent"] == "INVALID_REQUEST"
