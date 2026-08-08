from __future__ import annotations

import re

import tldextract

from app.core.config import settings

# Free/personal mailbox providers that cannot anchor a tenant. Registration
# requires a corporate domain; invited users are exempt from this check.
FREE_EMAIL_DOMAINS = frozenset(
    {
        # international
        "gmail.com",
        "googlemail.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "yahoo.com.cn",
        "ymail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "gmx.net",
        "mail.com",
        "zoho.com",
        # china
        "qq.com",
        "vip.qq.com",
        "foxmail.com",
        "163.com",
        "vip.163.com",
        "126.com",
        "vip.126.com",
        "yeah.net",
        "sina.com",
        "sina.cn",
        "sohu.com",
        "aliyun.com",
        "139.com",
        "189.cn",
        "wo.cn",
        # disposable (common)
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "temp-mail.org",
        "yopmail.com",
        "sharklasers.com",
        "dispostable.com",
        "getnada.com",
        "trashmail.com",
    }
)

_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PUBLIC_SUFFIX_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=(),
    include_psl_private_domains=True,
)


def _normalize_domain_name(raw_domain: str) -> str:
    try:
        domain = raw_domain.rstrip(".").encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("invalid email address") from exc
    labels = domain.split(".")
    if (
        len(domain) > 253
        or len(labels) < 2
        or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels)
    ):
        raise ValueError("invalid email address")
    return domain


def normalize_email_address(email: str) -> str:
    normalized = email.strip().lower()
    local, sep, raw_domain = normalized.rpartition("@")
    if (
        not sep
        or not local
        or len(local) > 64
        or "@" in local
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or any(character.isspace() or ord(character) < 32 for character in local)
    ):
        raise ValueError("invalid email address")
    domain = _normalize_domain_name(raw_domain)
    return f"{local}@{domain}"


def registrable_domain(raw_domain: str) -> str:
    host = _normalize_domain_name(raw_domain.strip().lower())
    extracted = _PUBLIC_SUFFIX_EXTRACTOR(host)
    registrable = getattr(extracted, "top_domain_under_public_suffix", None)
    if registrable is None:
        # tldextract < 5 compatibility for developer machines.
        registrable = extracted.registered_domain
    if registrable:
        return registrable.lower()
    if settings.allow_reserved_registration_domains:
        return host
    return ""


def email_domain(email: str) -> str:
    """Return the registrable company domain, not an arbitrary mail subdomain."""
    normalized = normalize_email_address(email)
    return registrable_domain(normalized.rsplit("@", 1)[1])


def company_domain(raw_domain: str) -> str:
    """Normalize an operator-supplied company domain into the form a tenant is
    keyed by. Accepts `acme.com`, `@acme.com` and `someone@acme.com`, and folds
    mail subdomains down to the registrable domain. Raises ValueError when the
    input cannot anchor a tenant: malformed, or a free mailbox provider — a
    company is not identified by `gmail.com`."""
    candidate = raw_domain.strip().lower().rpartition("@")[2]
    try:
        domain = registrable_domain(candidate)
    except ValueError as exc:
        raise ValueError("invalid company email domain") from exc
    if not domain or domain in FREE_EMAIL_DOMAINS:
        raise ValueError("invalid company email domain")
    return domain


def is_corporate_email(email: str) -> bool:
    """True if the email may anchor a new tenant registration."""
    try:
        normalized = normalize_email_address(email)
    except ValueError:
        return False
    allowlist: set[str] = set()
    for entry in settings.registration_email_allowlist:
        try:
            allowlist.add(normalize_email_address(entry))
        except ValueError:
            continue
    if normalized in allowlist:
        return True
    domain = email_domain(normalized)
    if not domain:
        return False
    return domain not in FREE_EMAIL_DOMAINS
