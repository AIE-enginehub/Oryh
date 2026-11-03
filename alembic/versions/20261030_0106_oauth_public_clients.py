"""Opt-in desktop OAuth public-client registration metadata."""
from alembic import op
from app.core.config import settings

revision = "20261030_0106"
down_revision = "20261028_0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'''create table "{schema}".oauth_public_clients (
        id uuid primary key,
        redirect_uris jsonb not null,
        client_name varchar(200) not null,
        created_at timestamptz not null default now()
    )''')


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(f'drop table "{schema}".oauth_public_clients')
