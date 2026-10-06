# -*- coding: utf-8 -*-
"""Deleting a product.

There was no way to do this at all, so a product entered twice had to be
removed by hand from outside the application — which happened three times in a
fortnight. What the system needed was not a general delete but a narrow one:
the empty twin goes, anything carrying stock or history stays.
"""

import pytest


@pytest.fixture()
def bits(db_session):
    from models import Color, Category, Size, SIZE_KIND_CAPACITY

    colour = Color(name="أسود", hex_code="#111111")
    category = Category(name="أغطية", sort_order=1)
    size = Size(name="1 لتر", kind=SIZE_KIND_CAPACITY)
    db_session.add_all([colour, category, size])
    db_session.commit()
    return {"colour": colour, "category": category, "size": size}


@pytest.fixture()
def empty_product(db_session, make_product, bits):
    product = make_product(name="منتج فاضي", color_id=bits["colour"].id)
    product.image = "orphan-candidate.webp"
    db_session.commit()
    return product


class TestDeletingAnEmptyProduct:

    def test_removes_it(self, empty_product, make_user, login):
        from models import Product

        product_id = empty_product.id
        response = login(make_user()).post(f"/product/{product_id}/delete")

        assert response.status_code == 302
        assert Product.query.get(product_id) is None

    def test_removes_its_empty_shelf_rows(
        self, db_session, empty_product, make_location, make_user, login
    ):
        from models import InventoryLocation

        make_location(empty_product, quantity=0, location="رف 5")
        db_session.commit()
        product_id = empty_product.id

        login(make_user()).post(f"/product/{product_id}/delete")

        assert InventoryLocation.query.filter_by(product_id=product_id).count() == 0

    def test_records_the_deletion(self, empty_product, make_user, login):
        from models import ActivityLog

        login(make_user()).post(f"/product/{empty_product.id}/delete")

        entry = ActivityLog.query.filter_by(action="DELETE_PRODUCT").first()
        assert entry is not None
        assert "منتج فاضي" in entry.description


class TestRefusals:
    """What must survive. Each of these is warehouse history."""

    def test_refuses_a_product_holding_stock(
        self, db_session, empty_product, make_location, make_user, login
    ):
        from models import Product

        make_location(empty_product, quantity=250)
        db_session.commit()
        product_id = empty_product.id

        login(make_user()).post(f"/product/{product_id}/delete")

        assert Product.query.get(product_id) is not None

    def test_refuses_a_product_with_movements(
        self, db_session, empty_product, make_location, make_user, login
    ):
        from models import Product, InventoryTransaction

        location = make_location(empty_product, quantity=0)
        db_session.add(InventoryTransaction(
            product_id=empty_product.id,
            location_id=location.id,
            transaction_type="IN",
            quantity=10,
        ))
        db_session.commit()
        product_id = empty_product.id

        login(make_user()).post(f"/product/{product_id}/delete")

        assert Product.query.get(product_id) is not None

    def test_says_why_it_refused(
        self, db_session, empty_product, make_location, make_user, login
    ):
        make_location(empty_product, quantity=250)
        db_session.commit()

        response = login(make_user()).post(
            f"/product/{empty_product.id}/delete", follow_redirects=True
        )
        body = response.get_data(as_text=True)

        assert "ما بينحذف" in body
        assert "250" in body

    def test_is_manager_only(self, empty_product, make_user, login):
        from models import Product

        product_id = empty_product.id
        staff = login(make_user(username="staff", role="STAFF"))
        staff.post(f"/product/{product_id}/delete")

        assert Product.query.get(product_id) is not None

    def test_requires_login(self, empty_product, client):
        response = client.post(f"/product/{empty_product.id}/delete")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_an_unknown_product_is_404(self, make_user, login):
        assert login(make_user()).post("/product/999999/delete").status_code == 404


class TestTheImage:

    def test_the_photo_goes_with_the_product(
        self, empty_product, make_user, login, monkeypatch
    ):
        deleted = []
        monkeypatch.setattr("routes.product_routes.delete_image", deleted.append)

        login(make_user()).post(f"/product/{empty_product.id}/delete")

        assert deleted == ["orphan-candidate.webp"]

    def test_a_photo_another_product_uses_is_kept(
        self, db_session, empty_product, make_product, bits, make_user, login,
        monkeypatch
    ):
        """Two rows can point at one file; deleting one must not break the other."""
        twin = make_product(name="منتج تاني", color_id=bits["colour"].id)
        twin.image = empty_product.image
        db_session.commit()

        deleted = []
        monkeypatch.setattr("routes.product_routes.delete_image", deleted.append)

        login(make_user()).post(f"/product/{empty_product.id}/delete")

        assert deleted == []


class TestTheButton:

    def test_offered_on_an_empty_product(self, empty_product, make_user, login):
        body = login(make_user()).get(
            f"/product/{empty_product.id}"
        ).get_data(as_text=True)

        assert f"/product/{empty_product.id}/delete" in body

    def test_hidden_when_the_product_holds_stock(
        self, db_session, empty_product, make_location, make_user, login
    ):
        # a button that always fails is a trap, not a feature
        make_location(empty_product, quantity=99)
        db_session.commit()

        body = login(make_user()).get(
            f"/product/{empty_product.id}"
        ).get_data(as_text=True)

        assert f"/product/{empty_product.id}/delete" not in body

    def test_its_confirmation_is_valid_javascript(
        self, empty_product, make_user, login
    ):
        r"""A real newline typed into the confirm() string instead of \n is a
        syntax error that kills every script on the page — and it is invisible
        until someone opens a product the button actually shows for. It has
        happened twice."""
        import re

        body = login(make_user()).get(
            f"/product/{empty_product.id}"
        ).get_data(as_text=True)

        handler = re.search(r'onsubmit="([^"]*)"', body)
        assert handler, "the delete form lost its confirmation"

        js = handler.group(1)
        assert "\n" not in js, "raw newline inside a JavaScript string literal"
        assert "\r" not in js
        assert js.count("'") % 2 == 0, "unbalanced quotes"

    def test_hidden_from_staff(self, empty_product, make_user, login):
        staff = login(make_user(username="staff", role="STAFF"))
        body = staff.get(f"/product/{empty_product.id}").get_data(as_text=True)

        assert f"/product/{empty_product.id}/delete" not in body
