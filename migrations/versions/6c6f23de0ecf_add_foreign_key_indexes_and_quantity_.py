"""add foreign key indexes and quantity check constraints

Postgres does not index foreign keys automatically, so every join on
product_id / warehouse_id / user_id was a sequential scan. Invisible at 138
transactions, expensive once a public storefront is reading the same tables.

The CHECK constraints move two rules that only lived in Python down into the
database, where no future code path can bypass them: stock never goes negative,
and a movement always has a positive quantity.

Revision ID: 6c6f23de0ecf
Revises: b1a04e152500
Create Date: 2026-08-30 12:17:12.563573

"""
from alembic import op


revision = '6c6f23de0ecf'
down_revision = 'b1a04e152500'
branch_labels = None
depends_on = None


# (index name, table, column)
INDEXES = [
    ("ix_activity_log_user_id", "activity_log", "user_id"),

    ("ix_inventory_location_product_id", "inventory_location", "product_id"),
    ("ix_inventory_location_warehouse_id", "inventory_location", "warehouse_id"),

    ("ix_inventory_transaction_product_id", "inventory_transaction", "product_id"),
    ("ix_inventory_transaction_location_id", "inventory_transaction", "location_id"),
    ("ix_inventory_transaction_destination_location_id",
     "inventory_transaction", "destination_location_id"),
    ("ix_inventory_transaction_user_id", "inventory_transaction", "user_id"),
    ("ix_inventory_transaction_customer_id", "inventory_transaction", "customer_id"),

    ("ix_notification_user_id", "notification", "user_id"),
    ("ix_notification_product_id", "notification", "product_id"),

    ("ix_product_category_id", "product", "category_id"),
    ("ix_product_size_id", "product", "size_id"),
    ("ix_product_neck_size_id", "product", "neck_size_id"),
    ("ix_product_color_id", "product", "color_id"),
    ("ix_product_secondary_color_id", "product", "secondary_color_id"),

    ("ix_stock_request_product_id", "stock_request", "product_id"),
    ("ix_stock_request_location_id", "stock_request", "location_id"),
    ("ix_stock_request_customer_id", "stock_request", "customer_id"),
    ("ix_stock_request_requested_by", "stock_request", "requested_by"),
    ("ix_stock_request_approved_by", "stock_request", "approved_by"),
]

# the unread-notifications badge runs on every page load
COMPOSITE = [
    ("ix_notification_user_unread", "notification", ["user_id", "is_read"]),
]

# (constraint name, table, condition)
CHECKS = [
    ("ck_inventory_location_quantity_non_negative",
     "inventory_location", "quantity >= 0"),
    ("ck_inventory_transaction_quantity_positive",
     "inventory_transaction", "quantity > 0"),
    ("ck_product_minimum_stock_non_negative",
     "product", "minimum_stock >= 0"),
]


def upgrade():
    for name, table, column in INDEXES:
        op.create_index(name, table, [column])

    for name, table, columns in COMPOSITE:
        op.create_index(name, table, columns)

    for name, table, condition in CHECKS:
        op.create_check_constraint(name, table, condition)


def downgrade():
    for name, table, _ in CHECKS:
        op.drop_constraint(name, table, type_="check")

    for name, table, _ in COMPOSITE:
        op.drop_index(name, table_name=table)

    for name, table, _ in INDEXES:
        op.drop_index(name, table_name=table)
