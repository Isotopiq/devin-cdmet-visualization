"""add generated reports

Revision ID: 0004
Revises: 3c5f09256469
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "3c5f09256469"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("report_type", sa.String(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_reports_project_id", "generated_reports", ["project_id"], unique=False)
    op.create_index("ix_generated_reports_dataset_id", "generated_reports", ["dataset_id"], unique=False)
    op.create_foreign_key("fk_generated_reports_project_id", "generated_reports", "projects", ["project_id"], ["id"])
    op.create_foreign_key("fk_generated_reports_dataset_id", "generated_reports", "datasets", ["dataset_id"], ["id"])
    op.create_foreign_key("fk_generated_reports_user_id", "generated_reports", "users", ["user_id"], ["id"])


def downgrade() -> None:
    op.drop_table("generated_reports")
