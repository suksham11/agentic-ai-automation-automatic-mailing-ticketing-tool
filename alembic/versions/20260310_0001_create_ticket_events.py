"""create ticket_events table

Revision ID: 20260310_0001
Revises:
Create Date: 2026-03-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260310_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("ticket_id", sa.String(length=128), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("subject", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("requires_handoff", sa.Boolean(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False, server_default=""),
        sa.Column("drafted_response", sa.Text(), nullable=False, server_default=""),
        sa.Column("cited_kb_files", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("ticket_events")
