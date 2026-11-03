"""Merge the agent-owned budget policy and desktop OAuth migration branches.

Keep both existing revisions intact so databases on either branch can advance
to the same head. The parent migrations perform their respective schema changes.
"""

revision = "20261101_0107"
down_revision = ("20261029_0106", "20261030_0106")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
