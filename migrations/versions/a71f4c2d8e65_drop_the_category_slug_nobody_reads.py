"""drop the category slug nobody reads

The column was added with the categories themselves, for URLs of the shape
/category/pumps that were never built. Categories are addressed by id
everywhere, and the name is what the pages show.

Nothing has ever read it. The only code that wrote it was
scripts/backfill_categories.py, seeding the ten values in
utils/categorization.py, and a category added through the interface since
then has carried a NULL slug without anything noticing — which is the
clearest evidence that no part of the system depends on it.

Revision ID: a71f4c2d8e65
Revises: c3a7d1e94b02
Create Date: 2026-11-11 12:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a71f4c2d8e65'
down_revision = 'c3a7d1e94b02'
branch_labels = None
depends_on = None


TABLE = "category"
COLUMN = "slug"
UNIQUE = "category_slug_key"


def upgrade():
    # The unique index goes with the column; dropping the column alone would
    # leave Postgres to remove it silently, and naming it here keeps the
    # downgrade symmetrical.
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.drop_column(TABLE, COLUMN)


def downgrade():
    # The column comes back empty. The ten values it held were not entered by
    # anyone: they were seeded from DEFAULT_CATEGORIES in
    # utils/categorization.py and are reproducible from there, so nothing is
    # lost that the repository does not still hold.
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=120), nullable=True))
    op.create_unique_constraint(UNIQUE, TABLE, [COLUMN])
