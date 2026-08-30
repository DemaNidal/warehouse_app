# -*- coding: utf-8 -*-
"""Form validation — the layer that decides what may reach the database."""

import pytest

from utils.validation.size import normalize_size_name, validate_size_name
from utils.validation.product import validate_product_form
from utils.validation.transaction import validate_transaction

BACKSLASH = chr(92)


class TestSizeNormalisation:

    @pytest.mark.parametrize("raw, expected", [
        ("28" + BACKSLASH + "410", "28/410"),
        ("28 / 410", "28/410"),
        ("  24" + BACKSLASH + "410  ", "24/410"),
        ("18/410", "18/410"),
        ("500 مل", "500 مل"),
        ("48.7 غم", "48.7 غم"),
    ])
    def test_neck_sizes_land_on_one_spelling(self, raw, expected):
        assert normalize_size_name(raw) == expected

    def test_a_backslash_can_never_be_stored(self):
        result = validate_size_name("33" + BACKSLASH + "400", "NECK")
        assert result.valid
        assert BACKSLASH not in result.data["name"]
        assert result.data["name"] == "33/400"


class TestSizeValidation:

    def test_kind_defaults_to_capacity(self):
        result = validate_size_name("750 مل")
        assert result.valid
        assert result.data["kind"] == "CAPACITY"

    def test_neck_kind_is_accepted(self):
        assert validate_size_name("38", "NECK").data["kind"] == "NECK"

    def test_unknown_kind_is_rejected(self):
        assert not validate_size_name("38", "SOMETHING").valid

    def test_empty_name_is_rejected(self):
        assert not validate_size_name("   ").valid

    def test_overlong_name_is_rejected(self):
        assert not validate_size_name("x" * 51).valid


class TestProductValidation:

    def _form(self, **overrides):
        form = {
            "name": "منتج",
            "color_id": "1",
            "size_id": "1",
            "neck_size_id": "",
            "category_id": "1",
            "minimum_stock": "10",
            "secondary_color_id": "",
        }
        form.update(overrides)
        return form

    def test_a_capacity_alone_is_enough(self):
        assert validate_product_form(self._form()).valid

    def test_a_neck_size_alone_is_enough(self):
        # a cap has no capacity, and that is correct
        result = validate_product_form(self._form(size_id="", neck_size_id="3"))
        assert result.valid
        assert result.data["size_id"] is None
        assert result.data["neck_size_id"] == 3

    def test_both_measurements_together_are_allowed(self):
        # the whole point of splitting size: a bottle records both
        result = validate_product_form(self._form(size_id="1", neck_size_id="3"))
        assert result.valid
        assert result.data["size_id"] == 1
        assert result.data["neck_size_id"] == 3

    def test_neither_measurement_is_rejected(self):
        result = validate_product_form(self._form(size_id="", neck_size_id=""))
        assert not result.valid

    def test_name_is_required(self):
        assert not validate_product_form(self._form(name="  ")).valid

    def test_negative_minimum_stock_is_rejected(self):
        assert not validate_product_form(self._form(minimum_stock="-1")).valid

    def test_same_colour_twice_is_rejected(self):
        result = validate_product_form(self._form(color_id="2", secondary_color_id="2"))
        assert not result.valid

    def test_category_is_optional(self):
        # the products entered before categories existed must still save
        result = validate_product_form(self._form(category_id=""))
        assert result.valid
        assert result.data["category_id"] is None

    def test_non_numeric_ids_are_rejected(self):
        assert not validate_product_form(self._form(size_id="abc")).valid


class TestTransactionValidation:

    def _form(self, **overrides):
        form = {"transaction_type": "IN", "location_id": "1", "quantity": "10", "notes": ""}
        form.update(overrides)
        return form

    def test_a_normal_movement_is_accepted(self):
        assert validate_transaction(self._form()).valid

    @pytest.mark.parametrize("quantity", ["0", "-5"])
    def test_non_positive_quantity_is_rejected(self, quantity):
        assert not validate_transaction(self._form(quantity=quantity)).valid

    def test_unknown_type_is_rejected(self):
        assert not validate_transaction(self._form(transaction_type="TELEPORT")).valid

    def test_outbound_requires_a_customer(self):
        # stock leaving the warehouse must be traceable to who took it
        assert not validate_transaction(self._form(transaction_type="OUT")).valid

    def test_outbound_with_a_customer_is_accepted(self):
        result = validate_transaction(self._form(transaction_type="OUT", customer_id="1"))
        assert result.valid

    def test_non_numeric_quantity_is_rejected(self):
        assert not validate_transaction(self._form(quantity="كتير")).valid
