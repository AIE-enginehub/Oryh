from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.request_context import resolved_base_url

logger = logging.getLogger("oryh.emails")


class EmailDeliveryError(RuntimeError):
    """An email could not be safely prepared or delivered.

    SMTP transport failures remain recorded in the outbox; configuration
    failures raised before message construction deliberately do not.
    """


@dataclass
class OutboundEmail:
    to: str
    subject: str
    body: str


def _send_smtp(message: OutboundEmail) -> None:
    import ssl
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import formataddr

    sender = settings.smtp_from or settings.smtp_user
    if not sender:
        raise EmailDeliveryError("smtp backend selected but smtp_from/smtp_user are not configured")
    if bool(settings.smtp_user) != bool(settings.smtp_password):
        raise EmailDeliveryError("smtp_user and smtp_password must be configured together")
    security = settings.smtp_security.strip().lower()
    if security not in {"ssl", "starttls"}:
        raise EmailDeliveryError("smtp_security must be 'ssl' or 'starttls'")

    mime = MIMEText(message.body, "plain", "utf-8")
    mime["Subject"] = message.subject
    mime["From"] = formataddr((settings.smtp_from_name, sender))
    mime["To"] = message.to
    try:
        smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if security == "starttls":
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(sender, [message.to], mime.as_string())
    except EmailDeliveryError:
        raise
    except Exception as exc:
        logger.error("smtp send failed to=%s subject=%r: %s", message.to, message.subject, exc)
        raise EmailDeliveryError(str(exc)) from exc


@dataclass
class EmailOutbox:
    """In-process outbox. Every message is recorded (tests read `messages` to
    capture links and passwords); the console backend additionally prints,
    the smtp backend delivers via the configured mailbox."""

    messages: list[OutboundEmail] = field(default_factory=list)

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = OutboundEmail(to=to, subject=subject, body=body)
        self.messages.append(message)
        if settings.email_backend == "smtp":
            _send_smtp(message)
        elif settings.email_backend == "console":
            # print instead of logger: uvicorn's default logging config drops
            # INFO records from application loggers, and the dev workflow
            # depends on seeing the verification/invite links.
            print(f"[oryh email] to={to} subject={subject!r}\n{body}", flush=True)

    def clear(self) -> None:
        self.messages.clear()


outbox = EmailOutbox()


def canonical_link_base(*, purpose: str) -> str:
    """Resolve the public origin for security-sensitive email links.

    Request-derived origins are convenient for local console output, but an
    operator can reach FastAPI directly on its development port where React is
    not served. SMTP delivery therefore fails closed unless deployment has
    declared its canonical browser origin.
    """
    configured_base = settings.base_url.strip()
    if settings.email_backend == "smtp" and not configured_base:
        raise EmailDeliveryError(
            f"ORYH_BASE_URL must be configured before SMTP {purpose} emails"
        )
    return configured_base.rstrip("/") if configured_base else resolved_base_url()


def send_verification_email(*, to: str, token: str) -> None:
    link = f"{canonical_link_base(purpose='verification')}/web/verify-email?token={token}"
    outbox.send(
        to=to,
        subject="Verify your oryh registration",
        body=(
            "Confirm your company email by opening the link below. After verification, "
            "a platform administrator will review your request before the company workspace is created.\n\n"
            f"{link}\n\n"
            "If you did not request this, ignore this email."
        ),
    )


def send_registration_approved_email(*, to: str, tenant_name: str) -> None:
    login_url = f"{canonical_link_base(purpose='registration approval')}/console/login"
    outbox.send(
        to=to,
        subject=f"您的 oryh 企业注册已通过 / {tenant_name} is ready on oryh",
        body=(
            f"您好！\n\n"
            f"您的公司「{tenant_name}」注册申请已通过审核，您是该工作空间的首位管理员。\n"
            f"请使用注册时设置的密码登录：{login_url}\n\n"
            f"登录后可在“访问凭证”中为 AI agent 创建个人或企业访问凭证。\n\n"
            f"---\n"
            f"Your registration for \"{tenant_name}\" was approved. You are its first workspace administrator.\n"
            f"Sign in at {login_url} with the password you chose during registration.\n"
        ),
    )


def send_registration_rejected_email(*, to: str, company_name: str, reason: str) -> None:
    outbox.send(
        to=to,
        subject=f"您的 oryh 企业注册未通过 / {company_name} registration update",
        body=(
            f"您好！\n\n"
            f"您的公司「{company_name}」注册申请未通过审核。\n"
            f"原因：{reason}\n\n"
            f"如需进一步核实，请联系平台运营人员。\n\n"
            f"---\n"
            f"Your registration for \"{company_name}\" was not approved.\n"
            f"Reason: {reason}\n"
        ),
    )


def send_enterprise_pilot_application_received_email(
    *, to: str, company_name: str, application_id: str
) -> None:
    outbox.send(
        to=to,
        subject=f"ORYH enterprise pilot application received / {company_name}",
        body=(
            f"We received the enterprise pilot application for \"{company_name}\".\n\n"
            f"Reference: {application_id}\n\n"
            "The ORYH platform team will review the company profile, agent landscape, "
            "and proposed first workflow. We will send the decision or any follow-up "
            "questions to this email address.\n\n"
            "If you did not submit this application, reply to the ORYH platform team."
        ),
    )


def send_enterprise_pilot_application_status_email(
    *,
    to: str,
    company_name: str,
    application_id: str,
    application_status: str,
    note: str | None,
) -> None:
    reference = f"Reference: {application_id}"
    operator_note = f"\n\nPlatform note: {note}" if note else ""
    if application_status == "accepted":
        registration_url = (
            f"{canonical_link_base(purpose='enterprise pilot acceptance')}/web/register"
        )
        subject = f"ORYH enterprise pilot application accepted / {company_name}"
        body = (
            f"The enterprise pilot application for \"{company_name}\" has been accepted.\n\n"
            f"{reference}{operator_note}\n\n"
            "The platform team will coordinate the readiness review and first-workflow scope. "
            "When requested, establish the company workspace through the reviewed registration "
            f"flow: {registration_url}"
        )
    elif application_status == "rejected":
        subject = f"ORYH enterprise pilot application update / {company_name}"
        body = (
            f"The enterprise pilot application for \"{company_name}\" will not move forward "
            f"at this time.\n\n{reference}{operator_note}"
        )
    else:
        subject = f"ORYH enterprise pilot application in review / {company_name}"
        body = (
            f"The ORYH platform team has started reviewing the enterprise pilot application "
            f"for \"{company_name}\" and may contact you for clarification.\n\n"
            f"{reference}{operator_note}"
        )
    outbox.send(to=to, subject=subject, body=body)


def send_tenant_welcome_email(*, to: str, tenant_name: str, password: str) -> None:
    login_url = f"{canonical_link_base(purpose='tenant welcome')}/console/login"
    outbox.send(
        to=to,
        subject=f"您的 oryh 工作空间「{tenant_name}」已开通 / Your oryh workspace is ready",
        body=(
            f"您好！\n\n"
            f"您的公司「{tenant_name}」已在 oryh 开通，您是该工作空间的管理员。\n\n"
            f"登录地址: {login_url}\n"
            f"登录账号: {to}\n"
            f"初始密码: {password}\n\n"
            f"请妥善保管，登录后建议尽快联系平台更换密码。\n\n"
            f"---\n"
            f"Your company \"{tenant_name}\" is now live on oryh and you are its admin.\n"
            f"Sign in at {login_url} with this email and the initial password above.\n"
        ),
    )


def send_password_reset_email(*, to: str, tenant_name: str, password: str) -> None:
    login_url = f"{canonical_link_base(purpose='password reset')}/console/login"
    outbox.send(
        to=to,
        subject=f"您在「{tenant_name}」的 oryh 密码已重置 / Your oryh password was reset",
        body=(
            f"您好！\n\n"
            f"您在「{tenant_name}」的 oryh 登录密码已由平台管理员重置，原有会话已全部退出。\n\n"
            f"登录地址: {login_url}\n"
            f"登录账号: {to}\n"
            f"新密码: {password}\n\n"
            f"如果这不是您请求的操作，请立即联系您的管理员。\n\n"
            f"---\n"
            f"A platform administrator reset your oryh password for \"{tenant_name}\"; "
            f"all existing sessions were signed out. Sign in at {login_url} with the new password above.\n"
        ),
    )


def send_password_reset_link_email(*, to: str, tenant_name: str, token: str) -> None:
    link = f"{canonical_link_base(purpose='password reset')}/web/invitations/accept?mode=reset&token={token}"
    outbox.send(
        to=to,
        subject=f"重置您在「{tenant_name}」的 oryh 密码 / Reset your oryh password",
        body=(
            f"您好！\n\n"
            f"有人请求重置您在「{tenant_name}」的 oryh 密码。\n\n"
            f"请打开以下一次性链接设置新密码：\n{link}\n\n"
            f"链接将在 {settings.password_reset_token_ttl_minutes} 分钟后失效。完成重置前，当前密码和会话仍然有效；"
            f"完成后，旧会话会全部退出。如果收到多封重置邮件，只有最新一封中的链接有效。\n\n"
            f"如果您没有预期此操作，请忽略本邮件并联系工作空间管理员。\n\n"
            f"---\n"
            f"A password reset was requested for your account in \"{tenant_name}\". "
            f"Open the one-time link above to choose a new password. Existing sessions are revoked only after the reset is completed; "
            f"if you receive multiple reset emails, only the newest link works.\n"
        ),
    )


def send_invitation_email(*, to: str, tenant_name: str, token: str) -> None:
    link = f"{canonical_link_base(purpose='invitation')}/web/invitations/accept?token={token}"
    outbox.send(
        to=to,
        subject=f"You are invited to join {tenant_name} on oryh",
        body=(
            f"You have been invited to join {tenant_name}.\n\n"
            f"Accept the invitation and set your password here:\n{link}\n\n"
            "If you did not expect this, ignore this email."
        ),
    )
