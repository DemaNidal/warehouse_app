# -*- coding: utf-8 -*-
"""Giving each product a reorder point of its own.

This script rewrites a column on every product in the catalogue, so what
matters is not only that the arithmetic is right but that it cannot quietly
undo a number a person chose, and that it can be put back.
"""

import importlib
import sys

import pytest


@pytest.fixture()
def script():
    sys.path.insert(0, "E:/warehouse_app/scripts")
    module = importlib.import_module("suggest_minimum_stock")
    return importlib.reload(module)


@pytest.fixture()
def ledger_path(script, tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    monkeypatch.setattr(script, "LEDGER", str(path))
    return path


@pytest.fixture()
def stocked(db_session, make_product, make_location):
    """Products at three different scales, each with arrivals recorded."""
    from models import InventoryTransaction
    from utils.search_text import refresh_search_text

    made = {}
    for key, name, batches, held in [
        ("big", "صنف كبير", [120_000, 120_000], 100_000),
        ("small", "صنف صغير", [400], 400),
        ("mid", "صنف وسط", [8_000, 10_000, 8_000], 9_000),
    ]:
        product = make_product(name=name, minimum_stock=1000)
        refresh_search_text(product)
        location = make_location(product, quantity=held, location="رف 2")
        for quantity in batches:
            db_session.add(InventoryTransaction(
                product_id=product.id,
                location_id=location.id,
                transaction_type="IN",
                quantity=quantity,
            ))
        made[key] = product

    db_session.commit()
    return made


class TestRounding:
    """A reorder point is read by a person, so it should look like a number
    a person would write."""

    @pytest.mark.parametrize("value,expected", [
        (0, 0),
        (4, 10),
        (37, 40),
        (196, 200),
        (1_873, 1_850),     # under 2,000 the step is 50, not 100
        (4_416, 4_400),
        (54_321, 54_000),
        (877_500 * 0.5, 440_000),
    ])
    def test_it_lands_on_round_numbers(self, script, value, expected):
        assert script.rounded(value) == expected

    def test_it_never_rounds_a_real_quantity_down_to_nothing(self, script):
        assert script.rounded(1) > 0
        assert script.rounded(0.4) > 0


class TestTheSuggestion:

    def test_it_scales_to_the_product(self, app, stocked, script):
        with app.app_context():
            rows = {r["name"]: r for r in script.suggestions()}

        assert rows["صنف كبير"]["suggested"] == 60_000
        assert rows["صنف وسط"]["suggested"] == 4_000
        assert rows["صنف صغير"]["suggested"] == 200

    def test_the_median_decides_not_the_largest(
        self, app, db_session, stocked, script
    ):
        """One freak delivery should not drag the threshold up with it."""
        from models import InventoryTransaction

        product = stocked["mid"]
        db_session.add(InventoryTransaction(
            product_id=product.id,
            location_id=product.locations[0].id,
            transaction_type="IN",
            quantity=900_000,
        ))
        db_session.commit()

        with app.app_context():
            rows = {r["name"]: r for r in script.suggestions()}

        # median of 8,000 / 8,000 / 10,000 / 900,000 is 9,000
        assert rows["صنف وسط"]["suggested"] == 4_500

    def test_outflows_are_not_mistaken_for_arrivals(
        self, app, db_session, stocked, script
    ):
        from models import InventoryTransaction

        product = stocked["small"]
        db_session.add(InventoryTransaction(
            product_id=product.id,
            location_id=product.locations[0].id,
            transaction_type="OUT",
            quantity=900_000,
        ))
        db_session.commit()

        with app.app_context():
            rows = {r["name"]: r for r in script.suggestions()}

        assert rows["صنف صغير"]["suggested"] == 200

    def test_a_product_with_no_arrivals_keeps_the_default(
        self, app, db_session, make_product, script
    ):
        from utils.search_text import refresh_search_text

        product = make_product(name="صنف بلا إدخال", minimum_stock=1000)
        refresh_search_text(product)
        db_session.commit()

        with app.app_context():
            rows = {r["name"]: r for r in script.suggestions()}

        assert rows["صنف بلا إدخال"]["suggested"] == script.FALLBACK
        assert "ما في إدخالات" in rows["صنف بلا إدخال"]["basis"]

    def test_it_reports_what_each_number_rests_on(
        self, app, stocked, script
    ):
        """Three quarters of the catalogue has exactly one arrival recorded,
        so the basis has to travel with the number."""
        with app.app_context():
            rows = {r["name"]: r for r in script.suggestions()}

        assert "1 إدخال" in rows["صنف صغير"]["basis"]
        assert "3 إدخال" in rows["صنف وسط"]["basis"]


class TestApplying:

    def test_a_dry_run_changes_nothing(self, app, db_session, stocked,
                                       script, ledger_path, monkeypatch):
        """Driven through main() rather than show(), because "write only on
        --commit" is decided in main() — testing show() leaves the one
        property that protects the catalogue unguarded."""
        from models import Product

        monkeypatch.setattr(sys, "argv", ["suggest_minimum_stock.py"])
        script.main()

        db_session.expire_all()
        assert all(
            Product.query.get(p.id).minimum_stock == 1000
            for p in stocked.values()
        )
        assert not ledger_path.exists()

    def test_the_commit_flag_is_what_writes(self, app, db_session, stocked,
                                            script, ledger_path, monkeypatch):
        from models import Product

        monkeypatch.setattr(
            sys, "argv", ["suggest_minimum_stock.py", "--commit"]
        )
        script.main()

        db_session.expire_all()
        assert Product.query.get(stocked["big"].id).minimum_stock == 60_000
        assert ledger_path.exists()

    def test_commit_writes_the_values(self, app, stocked, script,
                                      ledger_path):
        from models import Product

        with app.app_context():
            script.apply(script.suggestions(), script.load_ledger())
            assert Product.query.get(stocked["big"].id).minimum_stock == 60_000
            assert Product.query.get(stocked["small"].id).minimum_stock == 200

    def test_revert_puts_back_what_was_there(self, app, stocked, script,
                                             ledger_path):
        from models import Product

        with app.app_context():
            script.apply(script.suggestions(), script.load_ledger())
            script.apply(script.suggestions(), script.load_ledger(),
                         revert=True)

            assert all(
                Product.query.get(p.id).minimum_stock == 1000
                for p in stocked.values()
            )

    def test_running_it_twice_is_harmless(self, app, stocked, script,
                                          ledger_path):
        from models import Product

        with app.app_context():
            script.apply(script.suggestions(), script.load_ledger())
            first = Product.query.get(stocked["big"].id).minimum_stock
            script.apply(script.suggestions(), script.load_ledger())
            assert Product.query.get(stocked["big"].id).minimum_stock == first


class TestItDoesNotOverruleAPerson:
    """The edit screen lets her set any product's threshold by hand. A later
    run of this script must not quietly take that back."""

    def test_a_hand_set_value_survives_a_rerun(self, app, db_session,
                                               stocked, script, ledger_path):
        from models import Product

        with app.app_context():
            script.apply(script.suggestions(), script.load_ledger())

            product = Product.query.get(stocked["big"].id)
            product.minimum_stock = 12_345          # as if typed in the form
            db_session.commit()

            script.apply(script.suggestions(), script.load_ledger())

            assert Product.query.get(stocked["big"].id).minimum_stock == 12_345

    def test_revert_leaves_a_hand_set_value_alone(self, app, db_session,
                                                  stocked, script,
                                                  ledger_path):
        from models import Product

        with app.app_context():
            script.apply(script.suggestions(), script.load_ledger())

            product = Product.query.get(stocked["small"].id)
            product.minimum_stock = 77
            db_session.commit()

            script.apply(script.suggestions(), script.load_ledger(),
                         revert=True)

            assert Product.query.get(stocked["small"].id).minimum_stock == 77
