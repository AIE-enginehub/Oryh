from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import ALL_PERMISSIONS, SYSTEM_CAPABILITY_NAMES, permissions_cover, permissions_cover_any_scope
from app.core.request_context import resolved_api_base_url, resolved_base_url
from app.models import Role, Tenant, TenantSkill, TenantSkillAssignment, User
from app.services.provisioning import PRODUCT_SKILLS_DIR, read_skill_dir

# Placeholders rendered into skill files at download time. The registry only
# ever stores templates; a rendered bundle exists solely in the HTTP response.
PLACEHOLDERS = (
    "ORYH_BASE_URL",
    # The API root, rendered rather than derived. Most skills stated only
    # `base_url` and never mentioned `/api/v1` at all, so an agent's first call
    # went to the site root and came back 404 — recovered by a human telling it
    # the prefix, which is a human doing the bundle's job. Two facts the server
    # knows should not be one fact plus a convention the reader must supply.
    "ORYH_API_BASE_URL",
    "ORYH_API_KEY",
    "EMPLOYEE_ID",
    "USER_NAME",
    "TENANT_NAME",
    "TENANT_SLUG",
    "INSTALL_DIR",
)

# oryh-connect is the one skill that must work before any tenant is known and
# must serve EVERY employer the person has — so it is machine-level, not tenant
# data: it installs at the bundle root under the environment's brand
# ({brand}-connect), never tenant-namespaced. Every other skill is scoped to
# one company. (Registry/product-catalog name stays the canonical
# "oryh-connect"; the brand exists only in rendered output — the installed
# name, the frontmatter `name:`, and standalone product mentions in prose.)
SHARED_SKILLS = frozenset({"oryh-connect"})


def connect_install_name() -> str:
    """The bootstrap skill's on-disk name for THIS environment. Branded so a
    laptop connected to two servers (prod "oryh", test "calwbiz") keeps two
    distinct connect skills instead of clobbering one with the other."""
    return f"{settings.skill_brand}-connect"


def capability_covers(permissions: frozenset[str], required: str) -> bool:
    """A skill's required_capability is either a system verb — bare, or
    scoped like `business_object.write:daily_report`, in which case the
    scope must match exactly, via `verb:*`, or via the bare verb — or a
    custom capability (exact grant, scope-less by grammar)."""
    verb, _, scope = required.partition(":")
    if verb in SYSTEM_CAPABILITY_NAMES:
        if scope:
            return permissions_cover(permissions, verb, scope)
        # a skill gated on the BARE verb teaches the operations the API
        # allows under any scope of it: the purchase-contract desk holding
        # `contract.manage:purchase` must receive oryh-contracts, and the
        # API — not the bundle — is what keeps them to their scope
        # (review R12). Nobody is handed `:*` to make a download work.
        return permissions_cover_any_scope(permissions, verb)
    return required in permissions


def service_permissions() -> frozenset[str]:
    """What a tenant's own service key effectively holds for distribution.

    That principal BYPASSES permission checks rather than carrying grants
    (`has_permission` returns True outright), so its `Actor.permissions` is
    empty. Filtering a bundle by that empty set would hand the flow agent only
    the ungated skills — precisely not the gated flow skills it exists to run.

    Principals that do carry grants — a person's key, ORYH's hosted flow agent —
    are filtered by their own set instead; see `Actor.bypasses_permissions`.
    """
    return frozenset(ALL_PERMISSIONS)


def audience_by_skill(db: Session, tenant_id: str) -> dict[str, dict[str, set[str]]]:
    """{skill_id: {"user": {...}, "role": {...}}} in one read, so rendering a
    bundle costs the same whether the tenant targets nothing or everything."""
    audience: dict[str, dict[str, set[str]]] = {}
    rows = db.scalars(
        select(TenantSkillAssignment).where(TenantSkillAssignment.tenant_id == tenant_id)
    ).all()
    for row in rows:
        bucket = audience.setdefault(row.skill_id, {"user": set(), "role": set()})
        bucket.setdefault(row.subject_type, set()).add(row.subject_id)
    return audience


def can_run(skill: TenantSkill, permissions: frozenset[str]) -> bool:
    """Whether the capability axis lets this holder run the skill. A skill with
    no `required_capability` is ungated — not gated on the empty string, which
    `capability_covers` would (correctly) reject."""
    return skill.required_capability is None or capability_covers(permissions, skill.required_capability)


def role_permissions(db: Session, tenant_id: str) -> dict[str, frozenset[str]]:
    """{role name: its grants} — the lookup every distribution question needs,
    since a person's capability set is entirely their role's."""
    return {
        role.name: frozenset(role.permissions_jsonb or ())
        for role in db.scalars(select(Role).where(Role.tenant_id == tenant_id)).all()
    }


def eligible_skills(
    db: Session,
    tenant_id: str,
    permissions: frozenset[str],
    *,
    user_id: str | None = None,
    role: str | None = None,
    ignore_audience: bool = False,
) -> list[TenantSkill]:
    """Which active skills reach this holder.

    Two independent axes, composed with AND:

    - `required_capability` — may you do this at all. The server enforces it,
      so a skill delivered past this gate would only teach an agent to 403.
    - audience (`distribution_mode="targeted"`) — who is it for. Narrows the
      set the capability already allows; it can never widen it.

    `ignore_audience` is for the tenant service key: the flow agent has no
    user id and no role, and must keep receiving every flow skill — the same
    reason `service_permissions()` stands in for its empty grant set.
    """
    skills = db.scalars(
        select(TenantSkill)
        .where(TenantSkill.tenant_id == tenant_id, TenantSkill.status == "active")
        .order_by(TenantSkill.name.asc())
    ).all()
    audience = {} if ignore_audience else audience_by_skill(db, tenant_id)

    def in_audience(skill: TenantSkill) -> bool:
        if ignore_audience or skill.distribution_mode != "targeted":
            return True
        subjects = audience.get(skill.id)
        if not subjects:
            # targeted with nobody named reaches nobody — emptying an audience
            # narrows, it does not fall back to broadcasting
            return False
        return (user_id in subjects.get("user", ())) or (role in subjects.get("role", ()))

    return [
        skill
        for skill in skills
        if skill.name not in SHARED_SKILLS
        and can_run(skill, permissions)
        and in_audience(skill)
    ]


@dataclass(frozen=True)
class SkillReach:
    """One skill, and why it does or does not reach a subject."""

    skill: TenantSkill
    received: bool
    # received: capability | targeted_role | targeted_user
    # withheld: missing_capability | not_in_audience — EVERY one that applies
    reasons: tuple[str, ...]
    named_via: tuple[str, ...] = ()
    granted_by_roles: tuple[str, ...] = ()


def skill_reach(
    db: Session,
    tenant_id: str,
    permissions: frozenset[str],
    *,
    user_id: str | None = None,
    role: str | None = None,
    roles: dict[str, frozenset[str]] | None = None,
) -> list[SkillReach]:
    """Why each active skill does or does not reach this subject — the reverse
    of `eligible_skills`, for answering "why doesn't my agent have that skill".

    Today that question is only answerable by deriving the capability matrix by
    hand, which is why it usually goes unanswered.

    `received` is `eligible_skills`' verdict verbatim rather than a second
    implementation of the same rule: a troubleshooting view that disagrees with
    the bundle it describes is worse than no view at all. Everything else here
    only explains that verdict.

    A withheld skill reports EVERY reason that applies, not the first one. An
    earlier version named only the capability when a skill failed both axes,
    reasoning that an audience edit alone could not help. That is true and it
    is equally true in reverse — a capability grant alone cannot help either —
    so naming one reason sends whoever acts on it to make a change that leaves
    the skill exactly as unreachable as before. Both fixes are needed; both are
    reported.
    """
    received_ids = {
        skill.id
        for skill in eligible_skills(db, tenant_id, permissions, user_id=user_id, role=role)
    }
    skills = db.scalars(
        select(TenantSkill)
        .where(TenantSkill.tenant_id == tenant_id, TenantSkill.status == "active")
        .order_by(TenantSkill.name.asc())
    ).all()
    audience = audience_by_skill(db, tenant_id)
    grants_by_role = role_permissions(db, tenant_id) if roles is None else roles

    out: list[SkillReach] = []
    for skill in skills:
        # oryh-connect ships outside every tenant bundle, so reporting it as
        # withheld would be a lie about a skill the person already has
        if skill.name in SHARED_SKILLS:
            continue
        subjects = audience.get(skill.id, {})
        via: list[str] = []
        if user_id is not None and user_id in subjects.get("user", ()):
            via.append("user")
        if role is not None and role in subjects.get("role", ()):
            via.append(f"role:{role}")

        if skill.id in received_ids:
            reasons = []
            if "user" in via:
                reasons.append("targeted_user")
            if any(item.startswith("role:") for item in via):
                reasons.append("targeted_role")
            if not reasons:
                reasons.append("capability")
            out.append(
                SkillReach(
                    skill=skill, received=True, reasons=tuple(reasons), named_via=tuple(via)
                )
            )
            continue

        reasons = []
        holders: tuple[str, ...] = ()
        if not can_run(skill, permissions):
            reasons.append("missing_capability")
            holders = tuple(
                sorted(name for name, grants in grants_by_role.items() if can_run(skill, grants))
            )
        if skill.distribution_mode == "targeted" and not via:
            reasons.append("not_in_audience")
        out.append(
            SkillReach(
                skill=skill,
                received=False,
                reasons=tuple(reasons),
                granted_by_roles=holders,
            )
        )
    return out


def withheld_catalog(
    db: Session,
    tenant_id: str,
    permissions: frozenset[str],
    *,
    user_id: str | None,
    role: str | None,
    is_service: bool,
) -> list[dict]:
    """The skills this holder does NOT get, with enough to act on.

    A bundle used to describe only what it contained, which reads as a complete
    account of the workspace and is not one. An HR person asked to 做工资单 had
    no payroll skill, no mention that a payroll skill exists, and no way to
    reach one — so the agent improvised, filed the wrong kind of record, and
    nobody was told a capability was missing. The skill itself was fine: its
    description says 生成工资条, its body says a payslip is a `direction=payroll`
    invoice. It was simply never handed over, because the tenant's `hr_admin`
    role holds no payroll verb.

    `description` rides along because it is the sentence an agent matches a
    request against; a bare name is a thing the agent cannot connect to 工资单.

    A service key bypasses the permission layer, so nothing is withheld from it
    and an empty list is the truth rather than a gap.
    """
    if is_service:
        return []
    return [
        {
            "name": item.skill.name,
            "title": item.skill.title,
            "description": item.skill.description,
            "required_capability": item.skill.required_capability,
            "reasons": list(item.reasons),
            "granted_by_roles": list(item.granted_by_roles),
        }
        for item in skill_reach(
            db, tenant_id, permissions, user_id=user_id, role=role,
        )
        if not item.received
    ]


def withheld_section(withheld: list[dict], brand: str, root: str) -> str:
    """The README half that tells an agent what it is NOT equipped to do.

    Written as an instruction rather than a list, because the failure it
    prevents is an agent improvising: asked for something none of its skills
    cover, it invented a record shape instead of saying "I need a capability I
    do not have". A name and a description are enough for it to recognise the
    request and refuse it usefully.
    """
    if not withheld:
        return ""
    lines = [
        "## What you are NOT equipped to do\n\n",
        "This company also uses the skills below, and this bundle does **not** "
        "include them. If you are asked to do something one of these covers, do "
        "**not** improvise a way to record it — say which capability is missing "
        "and who can grant it. Filing the wrong kind of record is worse than "
        "not filing one, because it looks done.\n\n",
    ]
    for item in withheld:
        need = item.get("required_capability") or "—"
        holders = item.get("granted_by_roles") or []
        who = f"; held by: {', '.join(holders)}" if holders else ""
        lines.append(f"- **{item['name']}** — needs `{need}`{who}\n")
        if item.get("description"):
            lines.append(f"  - {excerpt(item['description'])}\n")
    lines.append(
        f"\nExcerpts only. `{root}/withheld.json` carries each description in "
        f"full, and `GET /api/v1/my/skills/reach` is the live version — it also "
        f"names an audience gap, which a capability grant alone would not fix.\n\n"
    )
    return "".join(lines)


# A narrow role withholds most of the catalog — nineteen of them for a plain
# member — and at full length that buried the install and security notes the
# README exists for, under a section nobody would read to the end of. These
# descriptions open with what the skill is for ("Use when HR … 生成工资条 …"),
# so the head is the part worth keeping.
EXCERPT_CHARS = 200


def excerpt(text: str) -> str:
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[:EXCERPT_CHARS].rstrip() + "…"


def tenant_slug(tenant: Tenant | None) -> str:
    """Every tenant created since the slug migration has one; the fallback keeps
    a legacy or fixture row from rendering an unnamed directory."""
    if tenant is None:
        return "unknown"
    return tenant.slug or f"t-{tenant.id[:8]}"


def install_dir(slug: str) -> str:
    """The bundle's single top-level directory — one per employer, so a second
    company's bundle lands beside the first instead of on top of it. Carries
    the environment's brand so a test server's bundle also lands beside the
    production one rather than on top of it."""
    return f"{settings.skill_brand}-skills-{slug}"


# Local agent runtimes commonly cap a skill's name at 64 characters; keep
# installed names safely under it (a slug can be 24 and a custom base 100).
MAX_INSTALLED_NAME = 63


def installed_skill_name(slug: str, name: str) -> str:
    """`oryh-timesheet-submit` → `{brand}-acme-timesheet-submit`. The company
    sits in the skill's own name because the name and description are all a
    local agent sees when it picks a skill from "报一下 Acme 这周的工时"; the
    brand sits in front of it so bundles from different environments (prod
    "oryh", test "calwbiz") stay distinguishable on the same machine. The
    canonical registry prefix being stripped is always `oryh-`, regardless of
    brand — registry names never change with the environment.

    This is the ideal name; `skill_name_map` is the source of truth because it
    also resolves the rare collision and over-length cases this cannot see on
    its own."""
    base = name[len("oryh-") :] if name.startswith("oryh-") else name
    return f"{settings.skill_brand}-{slug}-{base}"


def _shorten_installed_name(installed: str, registry_name: str) -> str:
    """Bring an over-length installed name under the limit without losing
    uniqueness: keep a readable head and append a digest of the registry name,
    which is itself unique per tenant."""
    if len(installed) <= MAX_INSTALLED_NAME:
        return installed
    tag = hashlib.sha256(registry_name.encode("utf-8")).hexdigest()[:6]
    return f"{installed[: MAX_INSTALLED_NAME - len(tag) - 1].rstrip('-')}-{tag}"


def skill_name_map(db: Session, tenant_id: str, slug: str) -> dict[str, str]:
    """Registry name → the name each skill installs under, for EVERY skill the
    tenant's registry knows — not just the ones this user is entitled to. A
    skill's prose may name a skill the reader lacks (a member's copy pointing at
    an approver's), and that reference must still say which company it means.

    This is the single source of truth for the on-disk name: both the zip
    directory and the manifest's `installed_as` come from here, so they cannot
    disagree and drive an endless re-download. Two guarantees the naive
    `oryh-<slug>-<base>` form cannot give alone:

    - **Injective.** A custom skill `my-work` and the product `oryh-my-work`
      both want `oryh-<slug>-my-work`; product skills keep the clean name and a
      colliding custom skill gets a deterministic digest suffix, so neither
      silently clobbers the other in the zip.
    - **Bounded length.** A custom name may be 100 chars; the installed name is
      shortened to stay under the runtime cap."""
    rows = db.execute(
        select(TenantSkill.name, TenantSkill.kind).where(
            TenantSkill.tenant_id == tenant_id, TenantSkill.status == "active"
        )
    ).all()
    # product skills first, then by name: the shipped catalog owns the clean
    # namespace, and the order is deterministic across renders
    ordered = sorted(
        ((name, kind) for name, kind in rows if name not in SHARED_SKILLS),
        key=lambda row: (0 if row[1] == "product" else 1, row[0]),
    )
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for name, _kind in ordered:
        target = _shorten_installed_name(installed_skill_name(slug, name), name)
        if target in used:
            tag = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
            target = _shorten_installed_name(f"{target}-{tag}", name + tag)
            while target in used:  # pathological; keep it terminating and unique
                target += "x"
        used.add(target)
        mapping[name] = target
    # The shared connect skill installs OUTSIDE the tenant directory, but prose
    # in tenant skills may still point at it (`oryh-connect` / $oryh-connect);
    # mapping it here lets rewrite_skill_references brand those pointers. It
    # never collides with tenant-skill targets (brand-connect vs brand-slug-*),
    # and skills_manifest never emits it — it iterates eligible skills only.
    connect_target = connect_install_name()
    while connect_target in used:  # pathological; keep it terminating
        connect_target += "x"
    mapping["oryh-connect"] = connect_target
    return mapping


def rewrite_skill_references(content: str, name_map: dict[str, str]) -> str:
    """Rewrite `$name` and `` `name` `` references to a skill's installed name.
    Both forms are delimited; a bare word is left alone, so a custom skill named
    for a common word (`report`) cannot corrupt that word — or an API field like
    `source_report_text` — elsewhere in the bundle.

    Longest name first: `oryh-business-object` is a strict prefix of
    `oryh-business-object-summary`, so the longer alternative must be tried
    first. Only delimited references are touched, so a custom skill named for a
    common word (`report`) cannot corrupt that word — or an API field that
    contains it — elsewhere in the bundle."""
    if not name_map:
        return content
    alternation = "|".join(re.escape(name) for name in sorted(name_map, key=len, reverse=True))
    sigil = re.compile(r"\$(" + alternation + r")(?![a-z0-9-])")
    backticked = re.compile(r"`(" + alternation + r")`")
    content = sigil.sub(lambda m: "$" + name_map[m.group(1)], content)
    content = backticked.sub(lambda m: "`" + name_map[m.group(1)] + "`", content)
    return content


# A standalone mention of the product name: "oryh" as its own word, in either
# prose case. Hyphenated identifiers are excluded here and handled by
# _BRAND_DERIVED / name_map instead; the `oryh.ai` domain is real regardless of
# environment. A sentence-final "…in oryh." still matches: the guard only
# excludes a dot that starts a domain label, not ordinary punctuation.
_PRODUCT_MENTION = re.compile(r"\b[Oo]ryh\b(?![-_])(?!\.[a-z0-9])")

# Paths and name TEMPLATES the bundle layout derives from the brand, which
# name_map cannot rewrite because they are not registry names: the install
# directory family (`oryh-skills-*/`, `oryh-skills-<slug>/`, legacy
# `oryh-skills/`), the bootstrap directory in any context (`oryh-connect/` —
# the backticked-name rule misses it because of the trailing slash), and the
# literal `<slug>` name template (`oryh-<slug>-skill-sync`).
#
# Leaving these canonical is what let a calwbiz-branded connect skill tell an
# agent to scan `oryh-skills-*/` — it then found the PRODUCTION deployment's
# directories and reported those companies as already connected here.
#
# `oryh-skill-sync` and `oryh-skill-author` do NOT match: `skills` requires the
# trailing "s", and those names continue with "skill-".
_BRAND_DERIVED = re.compile(r"\boryh-(skills|connect|<slug>)")


def apply_brand(content: str) -> str:
    """Rewrite every brand-derived string in rendered output. Two kinds:

    - **Derived paths and templates** (`oryh-skills-*/`, `oryh-connect/`,
      `oryh-<slug>-…`). These MUST follow the brand: they tell the agent which
      directories on disk belong to this deployment, and each environment's
      bundles live under their own brand. Getting this wrong is a correctness
      bug, not cosmetics — it makes one deployment's agent claim another's
      companies.
    - **Standalone prose mentions** ("submit your timesheet in oryh"), so a
      description does not steer "在 calwbiz 里报工时" away from the very
      bundle that serves it.

    Registry names and template hashes underneath stay canonical, exactly like
    installed names — the brand exists only in rendered output."""
    brand = settings.skill_brand
    if brand == "oryh":
        return content
    content = _BRAND_DERIVED.sub(lambda m: f"{brand}-{m.group(1)}", content)
    return _PRODUCT_MENTION.sub(
        lambda m: brand.capitalize() if m.group(0)[0] == "O" else brand, content
    )


def yaml_double_quoted(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + " ".join(escaped.split()) + '"'


def _is_single_line_scalar(value: str) -> bool:
    """True when a YAML value sits entirely on its own line, so replacing that
    one line is safe. A block scalar (`|`/`>`), an empty value (the real value
    is the indented block that follows), or a quote that opens without closing
    all continue onto later lines — rewriting only the first would orphan them
    and produce frontmatter the agent cannot parse."""
    value = value.strip()
    if not value:
        return False
    if value[0] in "|>":
        return False
    if value[0] in "\"'":
        return len(value) >= 2 and value[-1] == value[0]
    return True


def set_frontmatter_name(skill_md: str, installed_name: str) -> str:
    """Make the frontmatter `name:` the installed name. The frontmatter is the
    identity an agent runtime actually reads — leave the canonical registry
    name there and two employers' copies (or two environments' brands) present
    themselves as the SAME skill, undoing everything the directory name was
    scoped for. Rewritten to exactly the on-disk name so the two can never
    disagree. Emitted bare: installed names are validated kebab-case. Only a
    single-line scalar is touched, same contract as the description below."""
    lines = skill_md.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return skill_md
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() == "name":
            if not _is_single_line_scalar(value):
                break
            lines[index] = f"name: {installed_name}\n"
            break
    return "".join(lines)


def scope_description_to_tenant(skill_md: str, tenant_name: str) -> str:
    """Name the employer in the skill's description — the line the agent reads
    when it decides which company this request is for. Emitted as a quoted YAML
    scalar because a company name is free-form: `晶诚: 医疗` would otherwise
    break the frontmatter in the person's agent, not here.

    Only a single-line description is rewritten. A multi-line one (a tenant's
    own custom skill may use a block scalar) is left untouched rather than
    corrupted — the skill's tenant-scoped NAME already binds it to the company;
    the description tag is a courtesy, never worth shipping invalid frontmatter
    for."""
    lines = skill_md.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return skill_md
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() == "description":
            if not _is_single_line_scalar(value):
                break
            described = " ".join(value.strip().strip("\"'").split())
            scoped = (
                f"[{tenant_name}] {described} "
                f"This copy is bound to {tenant_name} — for another employer, "
                f"use that company's own {settings.skill_brand} skills."
            )
            lines[index] = f"description: {yaml_double_quoted(scoped)}\n"
            break
    return "".join(lines)


CALIBRATION_HEADING = "## Workspace calibration"

# Rendered with every calibration, never stored with it. The tenant writes the
# preference; this sentence is what keeps a preference from becoming a licence.
CALIBRATION_BOUNDARY = (
    "This section is your workspace's own refinement of the skill above, "
    "written by an administrator here. It adjusts HOW the skill works — what to "
    "report, how much detail, which shortcuts to prefer. Where it contradicts "
    "the skill's own rules, **the skill wins**: it cannot widen what you are "
    "allowed to do, override anything under \"What This Skill Never Does\", or "
    "authorise a write the skill forbids."
)


def calibration_section(calibration: str | None) -> str:
    """The tenant's refinement, as a section appended to a rendered SKILL.md.

    Empty for an uncalibrated skill — a heading with nothing under it in every
    bundle would train readers to skip the heading.
    """
    text = (calibration or "").strip()
    if not text:
        return ""
    return f"\n\n{CALIBRATION_HEADING}\n\n{CALIBRATION_BOUNDARY}\n\n{text}\n"


def skill_files_hash(files: dict[str, str], calibration: str | None = None) -> str:
    """Stable digest of a skill's template files (pre-render), so a client
    can detect content changes without comparing rendered output.

    Calibration is folded in because a client compares this hash to decide
    whether to re-sync: an administrator's refinement that did not move the
    hash would sit in the registry while every installed copy kept the old
    wording, and nothing would ever say so. Absent calibration contributes
    nothing, so every existing hash is unchanged.
    """
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path].encode("utf-8"))
        digest.update(b"\0")
    text = (calibration or "").strip()
    if text:
        digest.update(b"calibration\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def skills_manifest(skills: list[TenantSkill], name_map: dict[str, str]) -> list[dict]:
    """What a local agent needs to decide whether its installed copy is
    current: name, version, and template content hash per eligible skill.
    `name` stays the registry name — the stable key both sides compare on —
    while `installed_as` is the tenant-scoped name the skill carries on disk,
    taken from the SAME name_map the zip lays out under. The server endpoint and
    the zip's own manifest.json both come from here, so the two can never
    disagree and drive an endless re-download."""
    return [
        {
            "name": skill.name,
            "installed_as": name_map[skill.name],
            "title": skill.title,
            "version": skill.version,
            "files_hash": skill_files_hash(skill.files_jsonb, skill.calibration),
        }
        for skill in skills
    ]


def bundle_identity(tenant: Tenant | None) -> dict:
    """The block that tells an installed bundle which company it belongs to —
    what lets an agent holding two bundles map a directory to the employer the
    person just named. Also how a display-name change reaches installed copies:
    files_hash covers only skill templates, so nothing else would move."""
    slug = tenant_slug(tenant)
    return {
        "tenant": {
            "id": tenant.id if tenant else None,
            "slug": slug,
            "name": tenant.name if tenant else "",
        },
        # A sibling of `tenant`, never a member of it. Which machines serve the
        # workspace and which company the workspace IS are different questions,
        # and an agent given only the first answered the second with it.
        "environment_id": settings.environment_id or None,
        "install_dir": install_dir(slug),
        # Three keys for two facts. `site_base_url` is where a person opens the
        # console; `api_base_url` is where an agent sends calls. `base_url` is
        # the original name for the first, kept because already-installed
        # bundles read it — but its bare name is exactly what invited an agent
        # to treat the site root as the API root, so new readers are pointed at
        # the two explicit names and this one is documented as the alias.
        "base_url": resolved_base_url(),
        "site_base_url": resolved_base_url(),
        "api_base_url": resolved_api_base_url(),
    }


def render_content(content: str, context: dict[str, str]) -> str:
    for key, value in context.items():
        content = content.replace("{{" + key + "}}", value)
    return content


@dataclass(frozen=True)
class BundleFor:
    """Who a bundle is being rendered for. A person, or the tenant itself —
    the flow agent runs on the service key and needs its own copy of the flow
    skills, so the renderer must not assume there is a human behind it."""

    tenant_id: str
    display_name: str
    contact: str            # email, or the key's label for a service bundle
    role: str
    employee_id: str = ""
    user_id: str | None = None   # audience targeting names people by user id
    is_service: bool = False

    @classmethod
    def person(cls, user: User) -> "BundleFor":
        return cls(
            tenant_id=user.tenant_id,
            display_name=user.name or user.email,
            contact=user.email,
            role=user.role,
            employee_id=user.employee_id or "",
            user_id=user.id,
        )

    @classmethod
    def tenant_service(cls, tenant_id: str, label: str) -> "BundleFor":
        return cls(
            tenant_id=tenant_id,
            display_name=label,
            contact=label,
            role="service",
            is_service=True,
        )


def build_bundle_zip(
    db: Session,
    *,
    user: User | BundleFor,
    permissions: frozenset[str],
    api_key_plaintext: str,
) -> tuple[bytes, list[str]]:
    """Render the eligible skills with the holder's context and pack them as a
    zip. Returns (zip_bytes, skill_names).

    The zip has exactly one tenant directory — `oryh-skills-<slug>/` — plus the
    shared `oryh-connect/`. That directory IS the install root: an agent never
    computes it, it reads it, which is what lets someone employed by two
    companies install both bundles side by side.

    Nothing here touches the registry. Skills are stored under their canonical
    names and namespaced only on the way out — the ORM rows are live, so
    renaming one would flush the rename into the tenant's registry, and the
    template files_hash every client syncs on must stay tenant-independent."""
    holder = user if isinstance(user, BundleFor) else BundleFor.person(user)
    tenant = db.get(Tenant, holder.tenant_id)
    slug = tenant_slug(tenant)
    root = install_dir(slug)
    skills = eligible_skills(
        db, holder.tenant_id, permissions,
        user_id=holder.user_id, role=holder.role, ignore_audience=holder.is_service,
    )
    withheld = withheld_catalog(
        db, holder.tenant_id, permissions,
        user_id=holder.user_id, role=holder.role, is_service=holder.is_service,
    )
    name_map = skill_name_map(db, holder.tenant_id, slug)
    tenant_name = tenant.name if tenant else ""
    context = {
        "ORYH_BASE_URL": resolved_base_url(),
        "ORYH_API_BASE_URL": resolved_api_base_url(),
        "ORYH_API_KEY": api_key_plaintext,
        "EMPLOYEE_ID": holder.employee_id,
        "USER_NAME": holder.display_name,
        "TENANT_NAME": tenant_name,
        "TENANT_SLUG": slug,
        "INSTALL_DIR": root,
    }

    buffer = io.BytesIO()
    brand = settings.skill_brand
    connect_name = connect_install_name()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        kind = "tenant service" if holder.is_service else "personal"
        info = (
            f"# {brand} {kind} skill bundle — {tenant_name}\n\n"
            f"- for: {holder.display_name} <{holder.contact}>\n"
            f"- tenant: {tenant_name} (`{slug}`)\n"
            f"- role: {holder.role}\n"
            f"- generated: {generated_at}\n"
            f"- skills: {', '.join(name_map[s.name] for s in skills)}\n\n"
            f"{withheld_section(withheld, brand, root)}"
            f"## Install\n\n"
            f"This zip holds one company: extract `{root}/` into your local agent's "
            f"skills folder (WorkBuddy / OpenClaw compatible), replacing any earlier "
            f"`{root}/` wholesale. It also holds the shared `{connect_name}/`, which is "
            f"not company-specific — install it once, at the same level.\n\n"
            f"**Two employers, one agent**: every skill here is named "
            f"`{brand}-{slug}-…` and says so in its description, so asking your agent to "
            f"report hours for {tenant_name} reaches {tenant_name}'s {brand} and no one "
            f"else's. Never merge two companies' directories, and never edit a skill "
            f"to point at another company — the API key inside these files IS the "
            f"identity, and it belongs to {tenant_name}.\n\n"
            f"If a legacy unprefixed `oryh-skills/` directory is still installed, "
            f"delete it once this bundle is in place — it holds the same skills under "
            f"ambiguous names.\n\n"
            f"## Staying current\n\n"
            f"`{root}/manifest.json` records what is installed and which company it "
            f"belongs to; `{brand}-{slug}-skill-sync` compares it against "
            f"`GET /api/v1/my/skills/manifest` and re-downloads from "
            f"`GET /api/v1/my/skill-bundle` when anything changed — no admin needed, "
            f"and your key is NOT rotated by syncing.\n\n"
            f"## Security\n\n"
            f"These files embed YOUR personal {brand} API key for {tenant_name}. Treat "
            f"the bundle like a password: do not share or commit it. Asking an admin "
            f"for a new bundle rotates the key and invalidates this one immediately; "
            f"if that happens, reconnect from this device with the `{connect_name}` "
            f"skill.\n"
        )
        archive.writestr(f"{root}/README.md", info)
        if withheld:
            # Written only when there is something to say: an empty file in
            # every bundle would train readers to ignore it.
            archive.writestr(
                f"{root}/withheld.json",
                json.dumps(
                    {"generated_at": generated_at, "withheld": withheld},
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        archive.writestr(
            f"{root}/manifest.json",
            json.dumps(
                {
                    "generated_at": generated_at,
                    **bundle_identity(tenant),
                    "skills": skills_manifest(skills, name_map),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        for skill in skills:
            for path, content in skill.files_jsonb.items():
                rendered = apply_brand(
                    rewrite_skill_references(render_content(content, context), name_map)
                )
                if path == "SKILL.md":
                    rendered = set_frontmatter_name(rendered, name_map[skill.name])
                    rendered = scope_description_to_tenant(rendered, tenant_name)
                    # Last, so the workspace's refinement reads after the rules
                    # it refines — and so nothing above rewrites its wording.
                    rendered += calibration_section(skill.calibration)
                archive.writestr(f"{root}/{name_map[skill.name]}/{path}", rendered)
        # The bootstrap skill rides along so an admin-issued zip is enough to
        # get started, but it is rendered from the product catalog rather than
        # the tenant's registry and carries no key: it is the same file for
        # every company ON THIS SERVER, and the next employer's bundle from the
        # same environment overwrites it with an identical copy instead of
        # hijacking this one. Its installed name carries the environment brand,
        # so a second environment's connect lands beside it, not on top of it.
        # Only its self-references are rewritten — connect is tenant-agnostic
        # and must never absorb tenant-scoped names.
        connect_map = {"oryh-connect": connect_name}
        for path, content in read_skill_dir(PRODUCT_SKILLS_DIR / "oryh-connect").items():
            rendered = apply_brand(
                rewrite_skill_references(
                    render_content(content, {"ORYH_BASE_URL": context["ORYH_BASE_URL"]}),
                    connect_map,
                )
            )
            if path == "SKILL.md":
                rendered = set_frontmatter_name(rendered, connect_name)
            archive.writestr(f"{connect_name}/{path}", rendered)
    return buffer.getvalue(), [name_map[s.name] for s in skills]


def build_connect_skill_zip() -> bytes:
    """The credential-free bootstrap skill, standalone: no tenant or user is
    known at download time, so only the two address placeholders are rendered —
    the ones the server can always fill in for itself. Public and
    identical for every requester; nothing here is tenant data. Installed
    under the environment's brand ({brand}-connect) with self-references
    rewritten to match."""
    files = read_skill_dir(PRODUCT_SKILLS_DIR / "oryh-connect")
    context = {
        "ORYH_BASE_URL": resolved_base_url(),
        "ORYH_API_BASE_URL": resolved_api_base_url(),
    }
    connect_name = connect_install_name()
    connect_map = {"oryh-connect": connect_name}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            rendered = apply_brand(
                rewrite_skill_references(render_content(content, context), connect_map)
            )
            if path == "SKILL.md":
                rendered = set_frontmatter_name(rendered, connect_name)
            archive.writestr(f"{connect_name}/{path}", rendered)
    return buffer.getvalue()
