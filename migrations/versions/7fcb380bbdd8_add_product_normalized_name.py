"""add product normalized_name

The product name with its spelling folded — أ/إ/آ→ا, ة→ه, ى→ي, \\→/ — which is
what utils.categorization.normalize does in Python.

Grouping asks "is there another product with this name" every time a product
page is opened, and building the suggestions screen asks it for the whole
catalogue at once. Both used to answer by loading every product and folding the
names in Python: fine at a hundred rows, a full scan on every page view at ten
thousand. With the folded name stored and indexed, the first is one lookup and
the second is a GROUP BY.

The backfill repeats the folding in SQL so existing rows are correct the moment
the migration finishes, rather than waiting for someone to run a script.

Revision ID: 7fcb380bbdd8
Revises: 1821736b5a80
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa


revision = '7fcb380bbdd8'
down_revision = '1821736b5a80'
branch_labels = None
depends_on = None


# translate() maps character for character; the two strings pair up in order:
#   \→/   إ→ا   أ→ا   آ→ا   ى→ي   ة→ه
FOLD = (
    "lower("
    "regexp_replace("
    "translate(btrim(name), '\\إأآىة', '/ااايه'),"
    " '\\s+', ' ', 'g'"
    ")"
    ")"
)


def upgrade():
    op.add_column(
        "product",
        sa.Column("normalized_name", sa.String(length=255), nullable=True),
    )

    op.execute(f"UPDATE product SET normalized_name = {FOLD}")

    op.create_index(
        "ix_product_normalized_name", "product", ["normalized_name"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_product_normalized_name", table_name="product")
    op.drop_column("product", "normalized_name")
