# -*- coding: utf-8 -*-
"""Stopping a product from being entered twice.

The line this has to walk: the same name in another colour or size is a
different product and must go through untouched, while the same name in the
same colour and size is the same item twice and deserves a question. Three
duplicates in a week made the case for it.
"""

import pytest

from routes.product_routes import find_exact_twin


@pytest.fixture()
def bits(db_session):
    from models import Color, Category, Size, SIZE_KIND_CAPACITY, SIZE_KIND_NECK

    black = Color(name="أسود", hex_code="#000")
    red = Color(name="احمر", hex_code="#F00")
    category = Category(name="جلان", sort_order=9)
    five = Size(name="5 لتر", kind=SIZE_KIND_CAPACITY)
    ten = Size(name="10 لتر", kind=SIZE_KIND_CAPACITY)
    neck = Size(name="38", kind=SIZE_KIND_NECK)
    db_session.add_all([black, red, category, five, ten, neck])
    db_session.commit()
    return {"black": black, "red": red, "category": category,
            "five": five, "ten": ten, "neck": neck}


@pytest.fixture()
def existing(db_session, make_product, bits):
    product = make_product(name="جلن", color_id=bits["black"].id,
                           size_id=bits["five"].id, category_id=bits["category"].id)
    db_session.commit()
    return product


class TestFindExactTwin:

    def test_finds_the_identical_product(self, existing, bits):
        twin = find_exact_twin("جلن", bits["black"].id, bits["five"].id, None)
        assert twin is not None
        assert twin.id == existing.id

    def test_same_name_other_colour_is_not_a_twin(self, existing, bits):
        assert find_exact_twin("جلن", bits["red"].id, bits["five"].id, None) is None

    def test_same_name_other_capacity_is_not_a_twin(self, existing, bits):
        assert find_exact_twin("جلن", bits["black"].id, bits["ten"].id, None) is None

    def test_same_name_with_a_neck_added_is_not_a_twin(self, existing, bits):
        assert find_exact_twin("جلن", bits["black"].id, bits["five"].id, bits["neck"].id) is None

    def test_spelling_differences_still_match(self, existing, bits):
        # the same word with and without hamza is the same product
        assert find_exact_twin("جلن ", bits["black"].id, bits["five"].id, None) is not None

    def test_a_different_name_is_not_a_twin(self, existing, bits):
        assert find_exact_twin("جلن كبير", bits["black"].id, bits["five"].id, None) is None

    def test_can_exclude_the_product_itself(self, existing, bits):
        assert find_exact_twin("جلن", bits["black"].id, bits["five"].id, None,
                               exclude_id=existing.id) is None


class TestDuplicateCheckEndpoint:

    def test_requires_login(self, client):
        assert client.get("/products/duplicate-check").status_code == 302

    def test_reports_a_twin(self, existing, bits, make_user, login):
        response = login(make_user()).get("/products/duplicate-check", query_string={
            "name": "جلن", "color_id": bits["black"].id, "size_id": bits["five"].id,
        })
        body = response.get_json()

        assert body["duplicate"] is True
        assert body["id"] == existing.id
        assert body["name"] == "جلن"
        assert f"/product/{existing.id}" in body["url"]

    def test_stays_quiet_for_another_colour(self, existing, bits, make_user, login):
        body = login(make_user()).get("/products/duplicate-check", query_string={
            "name": "جلن", "color_id": bits["red"].id, "size_id": bits["five"].id,
        }).get_json()

        assert body == {"duplicate": False}

    def test_stays_quiet_with_nothing_to_compare(self, existing, make_user, login):
        body = login(make_user()).get("/products/duplicate-check").get_json()
        assert body == {"duplicate": False}


class TestAddProductBackstop:
    """What happens when the form's question was skipped — scripts off, or a
    double-click that fired two identical requests."""

    def payload(self, bits, **over):
        data = {
            "name": "جلن",
            "color_id": bits["black"].id,
            "secondary_color_id": "",
            "size_id": bits["five"].id,
            "neck_size_id": "",
            "category_id": bits["category"].id,
            "minimum_stock": "5",
        }
        data.update(over)
        return data

    def test_an_unconfirmed_twin_is_refused(self, existing, bits, make_user, login):
        from models import Product

        response = login(make_user()).post("/add-product", data=self.payload(bits))

        assert response.status_code == 302
        assert f"/product/{existing.id}" in response.headers["Location"]
        assert Product.query.filter_by(name="جلن").count() == 1

    def test_a_confirmed_twin_goes_through(self, existing, bits, make_user, login):
        from models import Product

        login(make_user()).post(
            "/add-product", data=self.payload(bits, confirm_duplicate="1")
        )

        assert Product.query.filter_by(name="جلن").count() == 2

    def test_another_colour_needs_no_confirmation(self, existing, bits, make_user, login):
        from models import Product

        login(make_user()).post(
            "/add-product", data=self.payload(bits, color_id=bits["red"].id)
        )

        assert Product.query.filter_by(name="جلن").count() == 2

    def test_two_identical_submissions_leave_one_product(
        self, bits, make_user, login
    ):
        """The double-click, as the server sees it."""
        from models import Product

        client = login(make_user())
        client.post("/add-product", data=self.payload(bits))
        client.post("/add-product", data=self.payload(bits))

        assert Product.query.filter_by(name="جلن").count() == 1


class TestForm:

    def test_carries_the_guard_fields(self, make_user, login, bits):
        body = login(make_user()).get("/add-product").get_data(as_text=True)

        assert 'name="confirm_duplicate"' in body
        assert 'id="saveProductBtn"' in body
        assert "/products/duplicate-check" in body
