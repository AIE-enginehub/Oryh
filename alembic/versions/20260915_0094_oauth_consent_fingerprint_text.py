"""oauth_authorization_codes.code_challenge becomes text

Revision ID: 20260915_0094
Revises: 20260910_0093
Create Date: 2026-09-15 10:00:00

The consent stage of `GET /oauth/authorize` (4fd7f55, first shipped in
v2026.9.5) stores `_consent_fingerprint(p)` in this column: all eight
authorization parameters joined by "|", so the consent POST can prove it
answers the page this session was shown. The column was `varchar(128)`, sized
for the PKCE challenge alone (43 characters). A real client's fingerprint
carries its client-id URL (the column beside it allows 500), its redirect URI
(1000), the resource URL and its `state`, which no specification bounds — so
every real authorization request failed with StringDataRightTruncation and
the page answered 500 on PostgreSQL. SQLite does not enforce VARCHAR lengths,
which is why the unit suite never saw it; the v2026.9.14.1 live probe did.

`text`, not a wider varchar: a width would only move the failure to the next
client with a longer `state`. `varchar` → `text` is a catalog change on
PostgreSQL; no row is rewritten.

Downgrade narrows the column back. Rows longer than 128 are consent nonces
and codes that live for minutes; they are deleted first so the narrowing
cannot fail on them.
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "20260915_0094"
down_revision = "20260910_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'alter table "{schema}".oauth_authorization_codes alter column code_challenge type text'
    )


def downgrade() -> None:
    schema = settings.database_schema.replace('"', '""')
    op.execute(
        f'delete from "{schema}".oauth_authorization_codes where length(code_challenge) > 128'
    )
    op.execute(
        f'alter table "{schema}".oauth_authorization_codes alter column code_challenge type varchar(128)'
    )
