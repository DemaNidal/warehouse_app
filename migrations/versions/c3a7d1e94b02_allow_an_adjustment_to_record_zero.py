"""allow an adjustment to record a count of zero

For every other movement the quantity is how much moved, so zero means
nothing happened and the CHECK is right to refuse it. For an adjustment the
number is the count found on the shelf, and a stock take that finds an empty
shelf is an ordinary morning.

Until now there was no way to record that. The only way to bring a shelf to
zero was an outbound movement for the whole amount, which puts stock that
never left the building into a customer's history and makes the movement log
describe something that did not happen.

Revision ID: c3a7d1e94b02
Revises: f5e88aadc891
Create Date: 2026-11-09 10:14:00.000000

"""
from alembic import op


revision = 'c3a7d1e94b02'
down_revision = 'f5e88aadc891'
branch_labels = None
depends_on = None


CONSTRAINT = "ck_inventory_transaction_quantity_positive"
TABLE = "inventory_transaction"

# An adjustment may be zero; nothing else may.
RELAXED = (
    "(transaction_type = 'ADJUSTMENT' AND quantity >= 0)"
    " OR (transaction_type <> 'ADJUSTMENT' AND quantity > 0)"
)

ORIGINAL = "quantity > 0"


def upgrade():
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, RELAXED)


def downgrade():
    # Deliberately does not delete anything. If zero-quantity adjustments
    # have been recorded by then, recreating the stricter rule fails and says
    # so — which is the right outcome. Throwing away recorded stock takes to
    # make a downgrade succeed quietly would be worse than the downgrade
    # stopping and asking.
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, ORIGINAL)
