from __future__ import annotations

from app.locales.zh_CN import messages as zh_messages

import logging
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.request_context import resolved_base_url

logger = logging.getLogger("oryh.emails")

# Backends whose bodies are already visible to whoever can see the process:
# `console` prints them, `memory` exists so tests can read them. For any other
# backend the body is a credential the outbox has no reason to hold.
BODY_VISIBLE_BACKENDS = frozenset({"console", "memory"})

# Enough to answer "did the last few go out"; short enough that a month-old
# process holds a bounded amount.
OUTBOX_LIMIT = 200


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
    """In-process record of what was sent.

    It used to keep every message forever, in every backend, body included —
    and the bodies are initial passwords, invite tokens and password-reset
    tokens. A long-lived production process therefore accumulated an unbounded
    plaintext credential store in memory, which nothing read and nothing ever
    trimmed. The 2026-08-16 architecture review's 5.3.

    Two rules now:

    * **Bodies are kept only for backends that already expose them.** `console`
      prints the body to stdout and `memory` exists to be read by tests, so
      retaining it there reveals nothing new. `smtp` — the production backend —
      records that the message went, to whom, and when, and drops the text.
    * **The record is bounded.** A ring buffer, so a process that runs for a
      month cannot grow one entry per email ever sent.

    A durable transactional outbox with async delivery is the right long-term
    answer and is a schema change; this is the part that does not need one.
    """

    # A list, not a deque: `messages == []` and slicing are what the suite and
    # the console read it with, and a container change that breaks those buys
    # nothing the explicit trim below does not.
    messages: list[OutboundEmail] = field(default_factory=list)

    def send(self, *, to: str, subject: str, body: str) -> None:
        retained = body if settings.email_backend in BODY_VISIBLE_BACKENDS else ""
        self.messages.append(OutboundEmail(to=to, subject=subject, body=retained))
        if len(self.messages) > OUTBOX_LIMIT:
            del self.messages[:-OUTBOX_LIMIT]
        if settings.email_backend == "smtp":
            _send_smtp(OutboundEmail(to=to, subject=subject, body=body))
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
        subject=f'{zh_messages.EMAILS_TEXT}{tenant_name} is ready on oryh',
        body=(
            f'{zh_messages.EMAILS_TEXT_2}{tenant_name}{zh_messages.EMAILS_TEXT_3}{login_url}{zh_messages.EMAILS_TEXT_4}{tenant_name}" was approved. You are its first workspace administrator.\nSign in at {login_url} with the password you chose during registration.\n'
        ),
    )


def send_registration_rejected_email(*, to: str, company_name: str, reason: str) -> None:
    outbox.send(
        to=to,
        subject=f'{zh_messages.EMAILS_TEXT_5}{company_name} registration update',
        body=(
            f'{zh_messages.EMAILS_TEXT_2}{company_name}{zh_messages.EMAILS_TEXT_6}{reason}{zh_messages.EMAILS_TEXT_7}{company_name}" was not approved.\nReason: {reason}\n'
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
    if not _zh():
        outbox.send(
            to=to,
            subject=f"Your Oryh workspace \"{tenant_name}\" is ready",
            body=(
                f"Your company \"{tenant_name}\" is now live on Oryh and you are its administrator.\n\n"
                f"Sign in: {login_url}\nAccount: {to}\nInitial password: {password}\n\n"
                f"Keep it safe and change it after your first sign-in.\n"
            ),
        )
        return
    outbox.send(
        to=to,
        subject=f'{zh_messages.EMAILS_TEXT_8}{tenant_name}{zh_messages.EMAILS_TEXT_9}',
        body=(
            f'{zh_messages.EMAILS_TEXT_2}{tenant_name}{zh_messages.EMAILS_TEXT_10}{login_url}{zh_messages.EMAILS_TEXT_11}{to}{zh_messages.EMAILS_TEXT_12}{password}{zh_messages.EMAILS_TEXT_13}{tenant_name}" is now live on oryh and you are its admin.\nSign in at {login_url} with this email and the initial password above.\n'
        ),
    )


def send_password_reset_email(*, to: str, tenant_name: str, password: str) -> None:
    login_url = f"{canonical_link_base(purpose='password reset')}/console/login"
    if not _zh():
        outbox.send(
            to=to,
            subject=f"Your Oryh password for \"{tenant_name}\" was reset",
            body=(
                f"An administrator reset your Oryh password for \"{tenant_name}\"; all existing sessions were signed out.\n\n"
                f"Sign in: {login_url}\nAccount: {to}\nNew password: {password}\n\n"
                f"If you did not ask for this, contact your administrator at once.\n"
            ),
        )
        return
    outbox.send(
        to=to,
        subject=f'{zh_messages.EMAILS_TEXT_14}{tenant_name}{zh_messages.EMAILS_TEXT_15}',
        body=(
            f'{zh_messages.EMAILS_TEXT_16}{tenant_name}{zh_messages.EMAILS_TEXT_17}{login_url}{zh_messages.EMAILS_TEXT_11}{to}{zh_messages.EMAILS_TEXT_18}{password}{zh_messages.EMAILS_TEXT_19}{tenant_name}"; all existing sessions were signed out. Sign in at {login_url} with the new password above.\n'
        ),
    )


def send_password_reset_link_email(*, to: str, tenant_name: str, token: str) -> None:
    link = f"{canonical_link_base(purpose='password reset')}/web/invitations/accept?mode=reset&token={token}"
    if not _zh():
        outbox.send(
            to=to,
            subject=f"Reset your Oryh password for \"{tenant_name}\"",
            body=(
                f"A password reset was requested for your account in \"{tenant_name}\".\n\n"
                f"Open this one-time link to choose a new password:\n{link}\n\n"
                f"The link expires in {settings.password_reset_token_ttl_minutes} minutes. Your current password and "
                f"sessions stay valid until the reset completes; afterwards every old session is signed out. "
                f"If you received several reset emails, only the newest link works.\n\n"
                f"If you did not expect this, ignore this email and tell your workspace administrator.\n"
            ),
        )
        return
    outbox.send(
        to=to,
        subject=f'{zh_messages.EMAILS_TEXT_20}{tenant_name}{zh_messages.EMAILS_TEXT_21}',
        body=(
            f'{zh_messages.EMAILS_TEXT_22}{tenant_name}{zh_messages.EMAILS_TEXT_23}{link}{zh_messages.EMAILS_TEXT_24}{settings.password_reset_token_ttl_minutes}{zh_messages.EMAILS_TEXT_25}{tenant_name}". Open the one-time link above to choose a new password. Existing sessions are revoked only after the reset is completed; if you receive multiple reset emails, only the newest link works.\n'
        ),
    )


def send_self_registration_notice_email(
    *, to: str, tenant_name: str, tenant_slug: str, admin_email: str
) -> None:
    """Tell a platform operator that a workspace created itself.

    With review switched off, mailbox verification alone provisions the
    tenant, and the review queue — which used to be how an operator learned a
    company had arrived — is empty. What the operator still owes the tenant is
    the hosted flow agent: provisioning writes its subscriptions, but the
    hosted key is minted by the platform and the runner learns of tenants from
    a credentials file. Until `enroll-hosted-flow-agent.sh` runs, that
    workspace's approval queues are enrolled on paper and driven by nobody.
    """
    if _zh():
        subject = f'{zh_messages.EMAILS_TEXT_26}{tenant_name}（{tenant_slug}）'
        body = (
            f'{zh_messages.EMAILS_TEXT_27}{tenant_name}{zh_messages.EMAILS_TEXT_28}{tenant_slug}{zh_messages.EMAILS_TEXT_29}{admin_email}{zh_messages.EMAILS_TEXT_30}{tenant_slug}{zh_messages.EMAILS_TEXT_31}'
        )
    else:
        subject = f"New workspace registered itself: {tenant_name} ({tenant_slug})"
        body = (
            f"A company registered through mailbox verification alone; its workspace exists and needed no review.\n\n"
            f"Company: {tenant_name}\nSlug: {tenant_slug}\nAdministrator: {admin_email}\n\n"
            f"Its hosted flow agent is not enrolled yet: provisioning wrote the subscriptions, but the hosted key is "
            f"minted by the platform and the runner learns of tenants from its credentials file. Run "
            f"enroll-hosted-flow-agent.sh {tenant_slug} from the environment directory; until then its approval "
            f"queues are enrolled on paper and driven by nobody.\n"
        )
    outbox.send(to=to, subject=subject, body=body)


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


# Work notifications: an assignment landed, a document came back, an approval
# finished. Sent by the server on the flow agent's behalf, because the agent's
# own runtime has no mail transport and deliberately never will — the pi
# child's environment is a six-variable whitelist, and widening it to carry
# SMTP credentials would hand a model process the mail server.
#
# The recipient is resolved from the employee record by the caller's API layer,
# never passed in. That turns "never guess an address" from a rule an agent has
# to remember into something it cannot do.

NOTIFICATION_SUBJECTS_ZH = {
    "assigned": zh_messages.EMAILS_NOTIFICATION_SUBJECTS_ZH,
    "assigned_many": zh_messages.EMAILS_NOTIFICATION_SUBJECTS_ZH_2,
    "returned": zh_messages.EMAILS_NOTIFICATION_SUBJECTS_ZH_3,
    "approved": zh_messages.EMAILS_NOTIFICATION_SUBJECTS_ZH_4,
    "rejected": zh_messages.EMAILS_NOTIFICATION_SUBJECTS_ZH_5,
}
NOTIFICATION_SUBJECTS_EN = {
    "assigned": "Work assigned to you: {title}",
    "assigned_many": "{count} items assigned to you",
    "returned": "Returned for rework: {title}",
    "approved": "Approved: {title}",
    "rejected": "Rejected: {title}",
}


def _zh() -> bool:
    """Whether the server writes Chinese. One content locale for everything the
    server itself says (seeds, catalogue, these mails): the hosted service is
    Chinese, a standalone deployment English unless ORYH_LOCALE says otherwise."""
    return settings.resolved_locale == "zh"


def send_work_notification(
    *,
    to: str,
    recipient_name: str,
    event: str,
    title: str,
    detail: str | None,
    actor_name: str | None,
    link: str,
    items: list[str] | None = None,
) -> None:
    """One work event, to the person it concerns.

    `items` is the list of what one run assigned to this person — one mail per
    recipient per run, each item on its own line, because the link below goes
    to their queue and not to any one item. `detail` is carried verbatim — for
    a return it is the approver's own comment, which is the instruction for
    what to fix. Summarising it would make it a different instruction, so
    nothing here reformats it.
    """
    if _zh():
        subjects, fallback = NOTIFICATION_SUBJECTS_ZH, zh_messages.EMAILS_SEND_WORK_NOTIFICATION_TEXT
        opening = f"{recipient_name}："
        said = {
            "assigned_many": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID, "assigned": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_2,
            "returned": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_3,
            "approved": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_4, "rejected": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_5,
            "actor": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_6, "detail": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_7, "link": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_8,
            "footer": zh_messages.EMAILS_SEND_WORK_NOTIFICATION_SAID_9,
        }
    else:
        subjects, fallback = NOTIFICATION_SUBJECTS_EN, "Work notification: {title}"
        opening = f"{recipient_name},"
        said = {
            "assigned_many": "{count} items were assigned to you:", "assigned": "Work was assigned to you: {title}",
            "returned": "Your \"{title}\" was returned and needs rework before you resubmit it.",
            "approved": "Your \"{title}\" was approved.", "rejected": "Your \"{title}\" was rejected.",
            "actor": "Handled by: {actor}", "detail": "Comment (verbatim):", "link": "Your queue: {link}",
            "footer": "Sent automatically by Oryh; do not reply to this email.",
        }
    subject = subjects.get(event, fallback).format(title=title)
    lines = [opening, ""]
    if event == "assigned" and items:
        subject = subjects["assigned_many"].format(count=len(items))
        lines.append(said["assigned_many"].format(count=len(items)))
        lines += [f"- {item}" for item in items]
    elif event in ("assigned", "returned", "approved", "rejected"):
        lines.append(said[event].format(title=title))
    else:
        lines.append(title)
    if actor_name:
        lines.append(said["actor"].format(actor=actor_name))
    if detail:
        lines += ["", said["detail"], detail]
    lines += ["", said["link"].format(link=link), "", said["footer"]]
    outbox.send(to=to, subject=subject, body="\n".join(lines))
