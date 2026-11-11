"""build the timezone marker with the schema

scripts/fix_timestamp_timezone.py shifts the rows written before the system
settled on UTC, and leaves a table behind so that running it twice cannot
shift the same rows twice. It creates that table itself, on the way out — so
the guard exists only on a database the script has actually been run against.

Rebuild the schema somewhere else and restore a backup into it, which is what
moving to another machine looks like, and the guard is not there. The data is
correct, because it was corrected before the backup was taken; but the first
person to run the script on the new machine is told nothing is done yet, and
every timestamp in the system moves a second time.

So the marker belongs to the schema, not to the script. The script still
writes it when it runs — this only makes sure it is never missing.

What the script asks is whether the table exists:

    select count(*) from information_schema.tables where table_name = ...

On a database built from these migrations the answer should be yes. Nothing
there was ever written in local time, so no correction is owed, and "already
applied" is the true answer rather than a convenient one.

Revision ID: d9b2e07c45f1
Revises: a71f4c2d8e65
Create Date: 2026-11-11 13:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd9b2e07c45f1'
down_revision = 'a71f4c2d8e65'
branch_labels = None
depends_on = None


TABLE = "timestamp_timezone_fixed"


def upgrade():
    bind = op.get_bind()

    # Production already has it, written by the script in September. Creating
    # it again would fail, and dropping and recreating it would throw away the
    # date it really happened.
    exists = bind.execute(sa.text(
        "select 1 from information_schema.tables"
        " where table_schema = 'public' and table_name = :name"
    ), {"name": TABLE}).scalar()

    if not exists:
        op.create_table(
            TABLE,
            sa.Column(
                "applied_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("(now() at time zone 'utc')"),
            ),
        )

    # A row so the marker reads the same either way. On a fresh database it
    # records when the question was settled, not a correction that happened:
    # nothing there was written in local time, so none was owed.
    empty = bind.execute(sa.text("select count(*) from %s" % TABLE)).scalar() == 0

    if empty:
        bind.execute(sa.text("insert into %s default values" % TABLE))


def downgrade():
    # Deliberately leaves the table where it is. Dropping it is precisely the
    # harm this migration exists to prevent: it re-arms a correction that has
    # already been made, and the next run of the script shifts every timestamp
    # in the system a second time. A downgrade is not worth that.
    pass
