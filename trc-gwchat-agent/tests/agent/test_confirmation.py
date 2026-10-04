from __future__ import annotations


import pytest

from trc_agent.services.confirmation import TicketError, TicketSigner, summarize
from tests.agent.helpers import signer


def test_roundtrip_binds_user_session_tool_and_args():
    sg = signer()
    p = sg.issue(user_id="u1", session_id="sess-0001", tool="send_provider_notification", args={"member_id": "HCC-2231087", "reason": "resend"})
    v = sg.verify(p.ticket, user_id="u1", session_id="sess-0001")
    assert v.tool == "send_provider_notification" and v.args["member_id"] == "HCC-2231087" and v.idempotency_key.startswith("tk-")
    assert "HCC-2231087" in p.summary


def test_tamper_detected():
    sg = signer()
    p = sg.issue(user_id="u1", session_id="sess-0001", tool="update_review_status", args={"member_id": "HCC-3345510"})
    body, sig = p.ticket.rsplit(".", 1)
    with pytest.raises(TicketError):
        sg.verify(body[:-2] + "AA." + sig, user_id="u1", session_id="sess-0001")


def test_other_user_or_session_rejected():
    sg = signer()
    p = sg.issue(user_id="u1", session_id="sess-0001", tool="send_provider_notification", args={})
    for u, s in [("u2", "sess-0001"), ("u1", "sess-9999")]:
        with pytest.raises(TicketError):
            sg.verify(p.ticket, user_id=u, session_id=s)


def test_expiry():
    sg = TicketSigner("k", ttl_s=-1)
    p = sg.issue(user_id="u", session_id="sess-0001", tool="x", args={})
    with pytest.raises(TicketError, match="expired"):
        sg.verify(p.ticket, user_id="u", session_id="sess-0001")


def test_different_secret_rejected():
    p = TicketSigner("a", 60).issue(user_id="u", session_id="sess-0001", tool="x", args={})
    with pytest.raises(TicketError):
        TicketSigner("b", 60).verify(p.ticket, user_id="u", session_id="sess-0001")


def test_idempotency_key_is_stable_per_ticket():
    sg = signer()
    p = sg.issue(user_id="u", session_id="sess-0001", tool="x", args={})
    assert sg.verify(p.ticket, user_id="u", session_id="sess-0001").idempotency_key == sg.verify(p.ticket, user_id="u", session_id="sess-0001").idempotency_key


def test_summaries_are_deterministic():
    assert "3 member(s)" in summarize("resend_notifications_bulk", {"member_ids": ["a", "b", "c"]})
