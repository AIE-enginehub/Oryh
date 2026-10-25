"""One project per deal; an undated customer relation is unique too

Revision ID: 20261019_0100
Revises: 20261015_0099
Create Date: 2026-10-19 22:30:00

Review 2026-10-19, F06 and F07.

* `projects_tenant_opportunity_uk`: a deal opens one project (plan
  2026-10-14). The bridge read, then inserted; two concurrent calls opened
  two. Partial, so projects with no deal are unaffected.
* `customer_relations_uk` becomes an expression index over
  `coalesce(effective_from, '0001-01-01')`. As a plain UNIQUE the NULL date
  made every undated copy of a relation distinct.

Rows that already break either rule are not merged here — which project or
which relation is the real one is the workspace's call. The migration
refuses with the counts per tenant instead, and the operator resolves them
in the console before running it again.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20261019_0100"
down_revision = "20261015_0099"
branch_labels = None
depends_on = None


def _refuse_if_any(bind, sql: str, what: str) -> None:
    rows = bind.exec_driver_sql(sql).all()
    if rows:
        listed = "; ".join(f"tenant {slug}: {count}" for slug, count in rows)
        raise RuntimeError(f"0100: {what} — resolve them in the console, then migrate again ({listed})")


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    bind = op.get_bind()
    _refuse_if_any(bind, f"""
        select t.slug, count(*) from (
          select tenant_id from "{schema}".projects
           where opportunity_id is not null
           group by tenant_id, opportunity_id having count(*) > 1
        ) d join "{schema}".tenants t on t.id = d.tenant_id
        group by t.slug order by t.slug
    """, "deals with more than one project")
    _refuse_if_any(bind, f"""
        select t.slug, count(*) from (
          select tenant_id from "{schema}".customer_relations
           where effective_from is null
           group by tenant_id, customer_id, related_customer_id, relation_type having count(*) > 1
        ) d join "{schema}".tenants t on t.id = d.tenant_id
        group by t.slug order by t.slug
    """, "undated customer relations recorded more than once")

    op.execute(
        f'create unique index if not exists projects_tenant_opportunity_uk on "{schema}".projects '
        f"(tenant_id, opportunity_id) where opportunity_id is not null"
    )
    op.execute(f'alter table "{schema}".customer_relations drop constraint if exists customer_relations_uk')
    op.execute(
        f'create unique index if not exists customer_relations_uk on "{schema}".customer_relations '
        f"(customer_id, related_customer_id, relation_type, coalesce(effective_from, '0001-01-01'::date))"
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop index if exists "{schema}".customer_relations_uk')
    op.execute(
        f'alter table "{schema}".customer_relations add constraint customer_relations_uk '
        f"unique (customer_id, related_customer_id, relation_type, effective_from)"
    )
    op.execute(f'drop index if exists "{schema}".projects_tenant_opportunity_uk')
