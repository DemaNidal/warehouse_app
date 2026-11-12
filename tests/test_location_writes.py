# -*- coding: utf-8 -*-
"""Adding a shelf to a product, and the movement that has to go with it.

Stock arriving somewhere is an event, so it is written twice: the quantity on
the shelf, and the IN movement that says where it came from. The two were
committed separately, which let the first stand without the second -- a shelf
holding 400 pieces that no movement accounts for, and a stock-take with
nothing to reconcile it against. Nobody would see it happen; it would show up
weeks later as a number that cannot be explained.
"""

import pytest

from models import InventoryLocation, InventoryTransaction, Warehouse


@pytest.fixture()
def warehouse(db_session):
    row = Warehouse(name="مستودع الرفوف")
    db_session.add(row)
    db_session.flush()
    return row


@pytest.fixture()
def manager(make_user):
    return make_user(username="shelf-manager", role="STORE_MANAGER")


class TestAddingAShelf:

    def test_the_shelf_and_the_movement_are_both_written(
        self, client, login, manager, make_product, warehouse, db_session
    ):
        product = make_product()
        login(manager)

        client.post("/product/%d/add-location" % product.id, data={
            "warehouse_id": warehouse.id,
            "quantity": "400",
            "location": "رف 7 خانة 2",
        })

        location = db_session.query(InventoryLocation).one()
        movement = db_session.query(InventoryTransaction).one()

        assert location.quantity == 400
        assert location.location == "رف 7 خانة 2"
        assert movement.location_id == location.id
        assert movement.transaction_type == "IN"
        assert movement.quantity == 400

    def test_an_empty_shelf_is_recorded_without_a_movement(
        self, client, login, manager, make_product, warehouse, db_session
    ):
        # a place kept for a product that is not there yet: nothing moved, so
        # there is nothing to explain
        product = make_product()
        login(manager)

        client.post("/product/%d/add-location" % product.id, data={
            "warehouse_id": warehouse.id,
            "quantity": "0",
            "location": "رف 7 خانة 3",
        })

        assert db_session.query(InventoryLocation).count() == 1
        assert db_session.query(InventoryTransaction).count() == 0


class TestTheTwoWritesAreOneAct:

    def test_no_shelf_is_left_behind_when_the_movement_fails(
        self, client, login, manager, make_product, warehouse,
        db_session, monkeypatch
    ):
        from routes import location_routes

        def refuse(*args, **kwargs):
            raise RuntimeError("the movement could not be written")

        monkeypatch.setattr(location_routes, "InventoryTransaction", refuse)

        product = make_product()
        login(manager)

        with pytest.raises(RuntimeError):
            client.post("/product/%d/add-location" % product.id, data={
                "warehouse_id": warehouse.id,
                "quantity": "400",
                "location": "رف 7 خانة 2",
            })

        # what the 500 handler does, and then the only question that matters:
        # is there stock on a shelf that nothing accounts for?
        db_session.rollback()

        assert db_session.query(InventoryLocation).count() == 0, \
            "400 pieces on a shelf with no movement to explain them"
        assert db_session.query(InventoryTransaction).count() == 0
