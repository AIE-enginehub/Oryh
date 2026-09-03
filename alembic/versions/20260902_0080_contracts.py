"""contracts: a file, and the clauses located inside it

Revision ID: 20260902_0080
Revises: 20260902_0079
Create Date: 2026-09-02 20:00:00

Not OFBiz's Agreement/AgreementItem/AgreementTerm. A contract is a header
(counterparty — a vendor OR a customer, the side derived; type, dates,
amounts; a supplement points at its parent), its originals as links into
the attachment store (any format, with the text an agent extracted from
each file kept beside it), what was agreed as lines, and the located
clauses: verbatim passages tagged by a tenant-extensible term type, each
pointing at the file and page it came from — so "付款节奏怎样" is one
lookup, never a re-read. Orders, invoices and payments gain a nullable
contract_id so execution under a contract is derived. The todo/approval
entity CHECKs re-derive to admit the new family.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings
from app.core.entity_types import APPROVAL_ENTITY_TYPES, TODO_ENTITY_TYPES


revision = "20260902_0080"
down_revision = "20260902_0079"
branch_labels = None
depends_on = None

TENANT_MATCH = "tenant_id::text = current_setting('app.tenant_id', true)"
PLATFORM_ON = "current_setting('app.is_platform_admin', true) = 'on'"


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _rls(schema: str, table: str) -> None:
    op.execute(f'create index if not exists {table}_tenant_idx on "{schema}".{table} (tenant_id)')
    op.execute(f'alter table "{schema}".{table} enable row level security')
    op.execute(f'drop policy if exists tenant_isolation on "{schema}".{table}')
    op.execute(
        f"""
        create policy tenant_isolation on "{schema}".{table}
          using ({TENANT_MATCH} or {PLATFORM_ON})
          with check ({TENANT_MATCH})
        """
    )


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f"""
        create table if not exists "{schema}".contracts (
          id uuid primary key,
          tenant_id uuid not null,
          contract_no varchar(64) not null,
          title varchar(200) not null,
          contract_type varchar(50) not null,
          vendor_id uuid references "{schema}".vendors (id),
          customer_id uuid references "{schema}".customers (id),
          counterparty_name_snapshot varchar(200),
          total_amount numeric(14, 2),
          currency varchar(3) not null default 'CNY',
          signed_date date,
          effective_from date,
          effective_to date,
          our_signatory varchar(100),
          counterparty_signatory varchar(100),
          employee_id uuid references "{schema}".employees (id),
          parent_contract_id uuid references "{schema}".contracts (id),
          summary text,
          status varchar(50) not null default 'draft',
          signed_at timestamptz,
          remarks text,
          custom_fields_jsonb jsonb not null default '{{}}'::jsonb,
          deleted_at timestamptz,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint contracts_contract_no_uk unique (tenant_id, contract_no),
          constraint contracts_one_counterparty_check check (vendor_id is null or customer_id is null)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".contract_items (
          id uuid primary key,
          tenant_id uuid not null,
          contract_id uuid not null references "{schema}".contracts (id),
          line_no integer,
          product_id uuid references "{schema}".products (id),
          description varchar(500),
          quantity numeric(14, 4),
          unit varchar(50),
          unit_price numeric(12, 2),
          currency varchar(3) not null default 'CNY',
          delivery_note varchar(500),
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".contract_documents (
          id uuid primary key,
          tenant_id uuid not null,
          contract_id uuid not null references "{schema}".contracts (id),
          attachment_id uuid not null references "{schema}".attachments (id),
          document_type varchar(50) not null default 'other',
          sort_order integer,
          page_no integer,
          caption varchar(200),
          extracted_text text,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint contract_documents_tenant_contract_attachment_uk
            unique (tenant_id, contract_id, attachment_id)
        )
        """
    )
    op.execute(
        f"""
        create table if not exists "{schema}".contract_terms (
          id uuid primary key,
          tenant_id uuid not null,
          contract_id uuid not null references "{schema}".contracts (id),
          term_type varchar(50) not null,
          clause_ref varchar(50),
          title varchar(200),
          content text not null,
          summary text,
          document_id uuid references "{schema}".contract_documents (id),
          page_no integer,
          sort_order integer,
          metadata_jsonb jsonb not null default '{{}}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        )
        """
    )
    for table, indexed in (
        ("contracts", ("vendor_id", "customer_id", "employee_id", "parent_contract_id")),
        ("contract_items", ("contract_id", "product_id")),
        ("contract_documents", ("contract_id", "attachment_id")),
        ("contract_terms", ("contract_id", "term_type", "document_id")),
    ):
        for column in indexed:
            op.execute(
                f'create index if not exists {table}_{column}_idx on "{schema}".{table} ({column})'
            )
        _rls(schema, table)
    for table in ("purchase_orders", "sales_orders", "invoices", "payments"):
        op.execute(
            f'alter table "{schema}".{table} add column if not exists '
            f'contract_id uuid references "{schema}".contracts (id)'
        )
        op.execute(
            f'create index if not exists {table}_contract_id_idx on "{schema}".{table} (contract_id)'
        )
    for table, name, allowed in (
        ("todos", "todos_entity_type_chk", TODO_ENTITY_TYPES),
        ("approval_records", "approval_records_entity_type_chk", APPROVAL_ENTITY_TYPES),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(allowed)}))"
        )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    keep_todo = tuple(t for t in TODO_ENTITY_TYPES if t != "contract")
    keep_approval = tuple(t for t in APPROVAL_ENTITY_TYPES if t != "contract")
    for table, name, keep in (
        ("todos", "todos_entity_type_chk", keep_todo),
        ("approval_records", "approval_records_entity_type_chk", keep_approval),
    ):
        op.execute(f'alter table "{schema}".{table} drop constraint if exists {name}')
        op.execute(
            f'alter table "{schema}".{table} add constraint {name} '
            f"check (entity_type in ({_quoted(keep)}))"
        )
    for table in ("purchase_orders", "sales_orders", "invoices", "payments"):
        op.execute(f'alter table "{schema}".{table} drop column if exists contract_id')
    op.execute(f'drop table if exists "{schema}".contract_terms')
    op.execute(f'drop table if exists "{schema}".contract_documents')
    op.execute(f'drop table if exists "{schema}".contract_items')
    op.execute(f'drop table if exists "{schema}".contracts')
