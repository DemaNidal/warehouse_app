"""add product_family

Groups a product sold in several colours or sizes under one row, so the
catalogue can show "غطاء قطرة، 3 ألوان" instead of three separate cards.

`product.family_id` is nullable and stays that way. An ungrouped product is
the normal case — nothing is forced into a family, and the whole feature can be
removed by dropping the column without touching a single row of stock.

Revision ID: 0adfd272e0d0
Revises: f5e88aadc891
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa


revision = '0adfd272e0d0'
down_revision = 'f5e88aadc891'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_family",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["category.id"],
            name="fk_product_family_category_id_category",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_family"),
    )

    op.add_column(
        "product",
        sa.Column("family_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_product_family_id_product_family",
        "product", "product_family",
        ["family_id"], ["id"],
    )

    # every grouped listing filters or joins on this
    op.create_index(
        "ix_product_family_id", "product", ["family_id"], unique=False
    )


def downgrade():
    op.drop_index("ix_product_family_id", table_name="product")
    op.drop_constraint(
        "fk_product_family_id_product_family", "product", type_="foreignkey"
    )
    op.drop_column("product", "family_id")
    op.drop_table("product_family")
