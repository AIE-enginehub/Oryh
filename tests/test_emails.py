from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.core.request_context import reset_request_base_url, set_request_base_url
from app.services import emails


@pytest.fixture(autouse=True)
def clear_outbox():
    emails.outbox.clear()
    yield
    emails.outbox.clear()


def test_verification_and_invitation_links_use_the_canonical_public_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "email_backend", "console")
    monkeypatch.setattr(settings, "base_url", "  https://public.oryh.test/  ")
    request_token = set_request_base_url("http://internal-host:8000")
    try:
        emails.send_verification_email(to="owner@example.com", token="verify-token")
        emails.send_invitation_email(
            to="member@example.com",
            tenant_name="Example",
            token="invite-token",
        )
    finally:
        reset_request_base_url(request_token)

    assert "https://public.oryh.test/web/verify-email?token=verify-token" in emails.outbox.messages[0].body
    assert "https://public.oryh.test/web/invitations/accept?token=invite-token" in emails.outbox.messages[1].body
    assert all("internal-host" not in message.body for message in emails.outbox.messages)


@pytest.mark.parametrize(
    ("send", "purpose"),
    [
        (
            lambda: emails.send_verification_email(
                to="owner@example.com",
                token="verify-token",
            ),
            "verification",
        ),
        (
            lambda: emails.send_invitation_email(
                to="member@example.com",
                tenant_name="Example",
                token="invite-token",
            ),
            "invitation",
        ),
    ],
)
def test_smtp_security_links_fail_closed_without_a_canonical_public_origin(
    monkeypatch: pytest.MonkeyPatch,
    send,
    purpose: str,
) -> None:
    smtp_attempts = []
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "base_url", "  ")
    monkeypatch.setattr(emails, "_send_smtp", lambda message: smtp_attempts.append(message))
    request_token = set_request_base_url("https://attacker.example")
    try:
        with pytest.raises(
            emails.EmailDeliveryError,
            match=rf"ORYH_BASE_URL must be configured before SMTP {purpose} emails",
        ):
            send()
    finally:
        reset_request_base_url(request_token)

    assert emails.outbox.messages == []
    assert smtp_attempts == []


def test_smtp_relay_uses_starttls_without_mailbox_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = MagicMock()
    server.__enter__.return_value = server
    smtp = MagicMock(return_value=server)
    monkeypatch.setattr("smtplib.SMTP", smtp)
    monkeypatch.setattr(settings, "smtp_host", "smtp-relay.gmail.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_security", "starttls")
    monkeypatch.setattr(settings, "smtp_from", "service@example.com")
    monkeypatch.setattr(settings, "smtp_user", None)
    monkeypatch.setattr(settings, "smtp_password", None)

    emails._send_smtp(
        emails.OutboundEmail(
            to="invitee@example.com",
            subject="Invitation",
            body="Open the invitation.",
        )
    )

    smtp.assert_called_once_with("smtp-relay.gmail.com", 587, timeout=15)
    assert server.ehlo.call_count == 2
    server.starttls.assert_called_once()
    server.login.assert_not_called()
    server.sendmail.assert_called_once()
    sender, recipients, raw_message = server.sendmail.call_args.args
    assert sender == "service@example.com"
    assert recipients == ["invitee@example.com"]
    assert "From: oryh <service@example.com>" in raw_message


def test_smtp_credentials_must_be_configured_as_a_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "smtp_from", "service@example.com")
    monkeypatch.setattr(settings, "smtp_user", "service@example.com")
    monkeypatch.setattr(settings, "smtp_password", None)

    with pytest.raises(
        emails.EmailDeliveryError,
        match="smtp_user and smtp_password must be configured together",
    ):
        emails._send_smtp(
            emails.OutboundEmail(
                to="invitee@example.com",
                subject="Invitation",
                body="Open the invitation.",
            )
        )
