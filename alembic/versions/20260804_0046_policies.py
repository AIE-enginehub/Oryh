"""规章制度: a published rule of the house

Revision ID: 20260804_0046
Revises: 20260803_0045
Create Date: 2026-08-04 09:00:00

One table.

`Content` + `DataResource` + `ContentRevision` + `ContentApproval` is OFBiz's
document half: a versioned text with `createdByUserLogin`, a `statusId`, a
`privilegeEnumId`, and — the field this whole change is named after —
`DataResource.isPublic`. `policies` keeps that shape and drops the CMS around
it: no `decoratorContentId`, no `childLeafCount`, no four-join read of one
paragraph. `isPublic` becomes three-valued, because 员工手册 (everyone),
薪酬管理办法 (management only) and 服务承诺 (customers too) are three different
answers and a boolean can hold two.

OFBiz's other half — `Agreement` + `AgreementTerm`, where each term is a
`termValue` / `textValue` / `minQuantity` / `maxQuantity` row — is deliberately
NOT reproduced, and the reason is the whole point of this system.

A term table exists because traditional software cannot read a policy. It has
to be told, in fields, that 一线城市住宿上限 is 600. The consumer here is an
agent that reads the paragraph, so the table would buy nothing and cost the
thing that matters: a SECOND SOURCE OF TRUTH for the same rule, free to drift
from the body it restates with nothing in the schema to notice.

So a workspace that wants the figures in a machine shape puts them in
`rules_json` on the policy row itself. It versions, publishes and freezes with
the document, because it IS the document — and the server never parses it, no
more than it parses `body` or a workflow definition.

The cost is stated plainly: changing one figure now means publishing a new
version of the policy that contains it, rather than closing one row. That is
how policy documents actually work, and it is what keeps the version history
from lying about what changed.

Status is a marker; the dates are the truth. `published` means "the current
version of this code" and is held by a partial unique index. What applied in
March is answered by the effective range across every non-draft version — the
same stance settlement takes, where `paid` is a marker and `outstanding_amount`
is the fact.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings


revision = "20260804_0046"
down_revision = "20260803_0045"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')

    op.execute(
        f"""
        create table if not exists "{schema}".policies (
          id uuid primary key,
          tenant_id uuid not null,
          -- the workspace's own 制度编号 (HR-001); versions share it
          code varchar(50) not null,
          version integer not null default 1,
          category varchar(30) not null,
          title varchar(200) not null,
          summary text,
          -- Markdown. The server never parses it, exactly as it never parses a
          -- workflow definition.
          body text not null,
          -- the same rules in whatever structure the workspace finds useful.
          -- Never parsed by the server; it has no more standing than `body`.
          rules_json jsonb,
          visibility varchar(20) not null default 'internal',
          required_capability varchar(100),
          status varchar(20) not null default 'draft',
          -- when it APPLIES, which is not when it was published
          effective_from date,
          effective_thru date,
          published_at timestamptz,
          published_by varchar(100),
          supersedes_id uuid references "{schema}".policies (id),
          attachment_id uuid references "{schema}".attachments (id),
          owner_employee_id uuid references "{schema}".employees (id),
          created_by varchar(100),
          deleted_at timestamptz,
          deleted_by varchar(100),
          delete_reason text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint policies_version_uk unique (tenant_id, code, version),
          constraint policies_visibility_ck check (
            visibility in ('internal', 'restricted', 'public')
          ),
          constraint policies_status_ck check (
            status in ('draft', 'published', 'superseded', 'repealed')
          ),
          -- a restricted policy naming no capability is readable by everyone,
          -- which is the opposite of what it says
          constraint policies_restricted_needs_capability_ck check (
            visibility <> 'restricted' or required_capability is not null
          ),
          -- who published it and when is the whole point of publishing it
          constraint policies_published_attribution_ck check (
            status <> 'published' or (published_at is not null and published_by is not null)
          ),
          constraint policies_effective_period_ck check (
            effective_thru is null or effective_from is null
            or effective_thru >= effective_from
          )
        )
        """
    )

    for statement in (
        f'create index if not exists policies_tenant_idx on "{schema}".policies (tenant_id)',
        f'create index if not exists policies_code_idx on "{schema}".policies (tenant_id, code, version)',
        'create index if not exists policies_category_idx on '
        f'"{schema}".policies (tenant_id, category, status)',
        f'create index if not exists policies_supersedes_idx on "{schema}".policies (supersedes_id)',
        f'create index if not exists policies_attachment_idx on "{schema}".policies (attachment_id)',
        f'create index if not exists policies_owner_idx on "{schema}".policies (owner_employee_id)',
        # one live version per 制度编号 — two documents both claiming to be the
        # current 报销制度 is the failure this table exists to prevent
        'create unique index if not exists policies_current_version_uk on '
        f'"{schema}".policies (tenant_id, code) '
        "where status = 'published' and deleted_at is null",
    ):
        op.execute(statement)

    op.execute(f'alter table "{schema}".policies enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".policies')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".policies
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    # `policy_rules` never shipped — an earlier draft of this same revision
    # created it before the second-source-of-truth problem was clear. Dropping
    # it here is what lets a database that ran that draft come back cleanly.
    op.execute(f'drop table if exists "{schema}".policy_rules')
    op.execute(f'drop table if exists "{schema}".policies')
