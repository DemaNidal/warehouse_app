# -*- coding: utf-8 -*-
"""Timestamps: stored in UTC, shown in local time.

The system used to write timestamps from two clocks. Columns defaulting to
`db.func.now()` took PostgreSQL's, running on GMT; columns defaulting to
`datetime.now` took the machine's, three hours ahead. A product created and
never touched read 11:12 created and 14:12 updated — the same instant.

What these tests hold down: one source for every column, and the offset applied
once, at display.
"""

from datetime import datetime, timezone

import pytest

from utils.clock import utcnow, to_local, local_to_utc, LOCAL_TZ


class TestUtcnow:

    def test_returns_utc_not_local(self):
        mine = utcnow()
        real_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        assert abs((mine - real_utc).total_seconds()) < 5

    def test_is_naive(self):
        # the columns are `timestamp without time zone`; a tz-aware value
        # would be silently converted on the way in
        assert utcnow().tzinfo is None


class TestDisplayConversion:

    def test_converts_utc_to_local(self):
        stored = datetime(2026, 9, 29, 11, 12)      # UTC, mid-summer
        assert to_local(stored).strftime("%H:%M") == "14:12"

    def test_winter_uses_the_winter_offset(self):
        # Palestine is +02 in December, not +03 — a fixed offset would be
        # wrong for half the year
        stored = datetime(2026, 12, 15, 12, 0)
        assert to_local(stored).strftime("%H:%M") == "14:00"

    def test_none_passes_through(self):
        # templates hand it columns that may be empty (approved_at, …)
        assert to_local(None) is None

    def test_round_trip_is_stable(self):
        local = datetime(2026, 9, 29, 14, 12)
        assert to_local(local_to_utc(local)).replace(tzinfo=None) == local


class TestLocalToUtc:
    """Used once, to correct rows written before the system settled on UTC."""

    def test_summer_shifts_three_hours(self):
        assert local_to_utc(datetime(2026, 8, 15, 14, 0)).hour == 11

    def test_winter_shifts_two_hours(self):
        assert local_to_utc(datetime(2026, 12, 15, 14, 0)).hour == 12

    def test_none_passes_through(self):
        assert local_to_utc(None) is None


class TestModelsAgree:
    """The defect itself: two columns on one row, written in one instant,
    disagreeing by the local offset."""

    def test_created_and_updated_match_on_a_fresh_row(
        self, db_session, make_product
    ):
        product = make_product(name="منتج توقيت")
        db_session.commit()

        gap = abs((product.updated_at - product.created_at).total_seconds())
        assert gap < 5, "created_at and updated_at came from different clocks"

    def test_a_product_and_its_transaction_agree(
        self, db_session, make_product, make_location
    ):
        from models import InventoryTransaction

        product = make_product(name="منتج حركة")
        location = make_location(product, quantity=10)
        db_session.flush()

        movement = InventoryTransaction(
            product_id=product.id,
            location_id=location.id,
            transaction_type="IN",
            quantity=5,
        )
        db_session.add(movement)
        db_session.commit()

        gap = abs((movement.created_at - product.created_at).total_seconds())
        assert gap < 5, "product and transaction came from different clocks"

    def test_stored_values_are_utc_not_local(self, db_session, make_product):
        product = make_product(name="منتج UTC")
        db_session.commit()

        real_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((product.created_at - real_utc).total_seconds()) < 10

    def test_every_timestamp_default_uses_one_source(self):
        """Guards the fix itself: a new column added with the old habit
        reintroduces exactly the bug this file exists for."""
        import io

        source = io.open("models.py", encoding="utf-8").read()

        assert "default=datetime.now" not in source
        assert "onupdate=datetime.now" not in source
        assert "default=db.func.now()" not in source
        assert "default=utcnow" in source


class TestTemplateFilter:

    def test_filter_is_registered(self, app):
        assert "local" in app.jinja_env.filters

    def test_filter_converts(self, app):
        rendered = app.jinja_env.from_string(
            "{{ (t | local).strftime('%H:%M') }}"
        ).render(t=datetime(2026, 9, 29, 11, 12))

        assert rendered == "14:12"

    def test_pages_show_local_time(self, db_session, make_product, make_user, login):
        """End to end: a row written now must read back as the wall clock."""
        import re

        product = make_product(name="منتج عرض")
        db_session.commit()

        body = login(make_user()).get(
            f"/product/{product.id}"
        ).get_data(as_text=True)

        expected = to_local(product.created_at).strftime("%Y-%m-%d %H:%M")
        assert expected in body
