"""add family suggestion dismissal

Grouping suggestions are recomputed from the catalogue each time the review
screen opens. Without somewhere to record a rejection, a proposal that was
looked at and turned down comes back on every visit, and a screen that keeps
asking an answered question stops getting read.

Revision ID: 1821736b5a80
Revises: 0adfd272e0d0
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa


revision = '1821736b5a80'
down_revision = '0adfd272e0d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "family_suggestion_dismissal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_family_suggestion_dismissal"),
        sa.UniqueConstraint(
            "normalized_name", name="uq_family_suggestion_dismissal_name"
        ),
    )


def downgrade():
    op.drop_table("family_suggestion_dismissal")
