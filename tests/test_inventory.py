# -*- coding: utf-8 -*-
"""Inventory movements — the part of the system that must never be wrong.

Stock numbers are what the business runs on: a silent off-by-one here is a
customer who does not get their order. These tests go through the real HTTP
routes rather than calling helpers, because that is where the guards live.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import db, InventoryLocation, InventoryTransaction, Customer


@pytest.fixture()
def admin(make_user):
    return make_user(username="admin-inv", role="ADMIN")


@pytest.fixture()
def customer(db_session):
    row = Customer(name="عميل اختبار")
    db_session.add(row)
    db_session.flush()
    return row


def qty(db_session, location_id):
    return db_session.get(InventoryLocation, location_id).quantity


# ============================================================
# database-level guarantees
# ============================================================

class TestDatabaseConstraints:
    """These rules must hold even if a future code path forgets to check."""

    def test_stock_cannot_go_negative(self, db_session, make_product, make_location):
        location = make_location(make_product(), quantity=5)

        with pytest.raises(IntegrityError):
            db_session.execute(
                text("update inventory_location set quantity = -1 where id = :i"),
                {"i": location.id},
            )
            db_session.flush()

    def test_a_movement_must_have_a_positive_quantity(
        self, db_session, make_product, make_location, admin
    ):
        product = make_product()
        location = make_location(product, quantity=10)

        with pytest.raises(IntegrityError):
            db_session.add(InventoryTransaction(
                product_id=product.id,
                location_id=location.id,
                transaction_type="IN",
                quantity=0,
                user_id=admin.id,
            ))
            db_session.flush()

    def test_minimum_stock_cannot_be_negative(self, db_session, make_product):
        product = make_product()

        with pytest.raises(IntegrityError):
            db_session.execute(
                text("update product set minimum_stock = -1 where id = :i"),
                {"i": product.id},
            )
            db_session.flush()


# ============================================================
# stock status thresholds
# ============================================================

class TestStockStatus:

    def test_zero_is_critical(self, make_product, make_location):
        product = make_product(minimum_stock=10)
        make_location(product, quantity=0)
        assert product.stock_status == "CRITICAL"

    def test_at_the_threshold_is_low(self, make_product, make_location):
        product = make_product(minimum_stock=10)
        make_location(product, quantity=10)
        assert product.stock_status == "LOW"

    def test_above_the_threshold_is_normal(self, make_product, make_location):
        product = make_product(minimum_stock=10)
        make_location(product, quantity=11)
        assert product.stock_status == "NORMAL"

    def test_total_adds_up_across_locations(self, make_product, make_location):
        product = make_product()
        make_location(product, quantity=100, warehouse_name="مستودع أ", location="A1")
        make_location(product, quantity=250, warehouse_name="مستودع ب", location="B2")
        assert product.total_quantity == 350


# ============================================================
# movements through the real routes
# ============================================================

class TestStockMovements:

    def _post(self, client, product, **data):
        return client.post(
            f"/product/{product.id}/transaction/add",
            data=data,
            follow_redirects=True,
        )

    def test_inbound_raises_the_count(
        self, db_session, client, login, admin, make_product, make_location
    ):
        product = make_product()
        location = make_location(product, quantity=100)
        login(admin)

        self._post(client, product,
                   transaction_type="IN", location_id=location.id, quantity="50")

        assert qty(db_session, location.id) == 150

    def test_outbound_lowers_the_count(
        self, db_session, client, login, admin, customer, make_product, make_location
    ):
        product = make_product()
        location = make_location(product, quantity=100)
        login(admin)

        self._post(client, product, transaction_type="OUT",
                   location_id=location.id, quantity="30", customer_id=customer.id)

        assert qty(db_session, location.id) == 70

    def test_taking_more_than_there_is_changes_nothing(
        self, db_session, client, login, admin, customer, make_product, make_location
    ):
        product = make_product()
        location = make_location(product, quantity=40)
        login(admin)

        response = self._post(client, product, transaction_type="OUT",
                              location_id=location.id, quantity="100",
                              customer_id=customer.id)

        assert qty(db_session, location.id) == 40, "المخزون تغيّر رغم رفض الحركة"
        assert "الكمية غير كافية" in response.get_data(as_text=True)

    def test_a_rejected_movement_leaves_no_record(
        self, db_session, client, login, admin, customer, make_product, make_location
    ):
        product = make_product()
        location = make_location(product, quantity=40)
        login(admin)

        self._post(client, product, transaction_type="OUT",
                   location_id=location.id, quantity="100", customer_id=customer.id)

        recorded = db_session.query(InventoryTransaction).filter_by(
            product_id=product.id
        ).count()
        assert recorded == 0

    def test_taking_exactly_what_is_left_is_allowed(
        self, db_session, client, login, admin, customer, make_product, make_location
    ):
        product = make_product()
        location = make_location(product, quantity=40)
        login(admin)

        self._post(client, product, transaction_type="OUT",
                   location_id=location.id, quantity="40", customer_id=customer.id)

        assert qty(db_session, location.id) == 0

    def test_every_movement_is_recorded(
        self, db_session, client, login, admin, make_product, make_location
    ):
        product = make_product()
        location = make_location(product, quantity=10)
        login(admin)

        self._post(client, product,
                   transaction_type="IN", location_id=location.id, quantity="25")

        movement = db_session.query(InventoryTransaction).filter_by(
            product_id=product.id
        ).one()
        assert movement.quantity == 25
        assert movement.transaction_type == "IN"
        assert movement.user_id == admin.id


class TestTransfers:

    def test_a_transfer_moves_stock_without_creating_any(
        self, db_session, client, login, admin, make_product, make_location
    ):
        product = make_product()
        source = make_location(product, quantity=100, warehouse_name="أ", location="A1")
        target = make_location(product, quantity=20, warehouse_name="ب", location="B1")
        before = product.total_quantity

        login(admin)
        client.post(f"/product/{product.id}/transfer", data={
            "source_location_id": source.id,
            "destination_location_id": target.id,
            "quantity": "40",
        }, follow_redirects=True)

        assert qty(db_session, source.id) == 60
        assert qty(db_session, target.id) == 60

        db_session.refresh(product)
        assert product.total_quantity == before, "التحويل غيّر الإجمالي"

    def test_a_transfer_bigger_than_the_source_is_refused(
        self, db_session, client, login, admin, make_product, make_location
    ):
        product = make_product()
        source = make_location(product, quantity=30, warehouse_name="أ", location="A1")
        target = make_location(product, quantity=0, warehouse_name="ب", location="B1")

        login(admin)
        client.post(f"/product/{product.id}/transfer", data={
            "source_location_id": source.id,
            "destination_location_id": target.id,
            "quantity": "100",
        }, follow_redirects=True)

        assert qty(db_session, source.id) == 30
        assert qty(db_session, target.id) == 0
