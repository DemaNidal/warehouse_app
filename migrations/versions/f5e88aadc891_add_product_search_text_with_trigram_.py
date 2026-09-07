"""add product search_text with trigram index

`ILIKE '%…%'` cannot use a normal B-tree index — Postgres reads every row and
compares. Fine at a hundred products, not at several thousand with people
typing in the box. pg_trgm indexes the three-character sequences in a string,
which is exactly what a partial match needs.

The column itself is filled by utils.search_text and holds normalised words, so
"اسود" finds "أسود" — the spelling is settled before it is ever stored.

Revision ID: f5e88aadc891
Revises: 6c6f23de0ecf
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa


revision = 'f5e88aadc891'
down_revision = '6c6f23de0ecf'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column("product", sa.Column("search_text", sa.Text(), nullable=True))

    op.execute(
        "CREATE INDEX ix_product_search_text_trgm "
        "ON product USING gin (search_text gin_trgm_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_product_search_text_trgm")
    op.drop_column("product", "search_text")
    # pg_trgm is left installed: other things may come to rely on it, and
    # dropping an extension is not something a migration should decide.
