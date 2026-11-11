# -*- coding: utf-8 -*-
"""Three things the application got wrong in ordinary daily use.

None of them looked like a bug from the inside — each one answered, just
with the wrong answer:

  * renaming a colour left every product that carries it searchable only
    under the spelling nobody was going to type again;
  * a date filter compared a local day against a UTC column, so the first
    hours of the day belonged to the day before;
  * a stock take that found a shelf empty could not be written down, because
    an adjustment of zero was refused as if it were a movement of nothing.
"""

from datetime import datetime

import pytest
from sqlalchemy import text

from models import Color, Product, Size, SIZE_KIND_NECK
from utils.clock import local_day_bounds, local_to_utc
from utils.validation.transaction import validate_transaction


# ------------------------------------------------- a rename reaches the index

class TestRenamingAColourRewritesItsProducts:

    def test_the_old_spelling_is_gone_and_the_new_one_is_there(
        self, client, login, make_user, make_product, db_session
    ):
        colour = db_session.query(Color).first()
        if colour is None:
            colour = Color(name="أزرق", hex_code="#2563EB")
            db_session.add(colour)
            db_session.flush()

        colour.name = "أزرق"
        product = make_product(name="غطاء", color_id=colour.id)
        db_session.flush()

        from utils.search_text import refresh_search_text
        refresh_search_text(product)
        db_session.commit()

        assert "ازرق" in product.search_text

        login(make_user(role="ADMIN"))
        response = client.post(
            f"/color/{colour.id}/edit",
            data={"name": "تركواز", "hex_code": "#14B8A6"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)

        assert "تركواز" in refreshed.search_text, \
            "الاسم الجديد لازم يوصل لعمود البحث بدون ما حدا يشغّل سكربت"
        assert "ازرق" not in refreshed.search_text, \
            "الاسم القديم لازم يختفي، مش يضل محجوز بالعمود"

    def test_a_secondary_colour_counts_too(
        self, client, login, make_user, make_product, db_session
    ):
        primary = Color(name="أبيض", hex_code="#F8FAFC")
        secondary = Color(name="ذهبي", hex_code="#D4AF37")
        db_session.add_all([primary, secondary])
        db_session.flush()

        product = make_product(name="جار", color_id=primary.id)
        product.secondary_color_id = secondary.id
        db_session.flush()

        from utils.search_text import refresh_search_text
        refresh_search_text(product)
        db_session.commit()

        login(make_user(role="ADMIN"))
        client.post(
            f"/color/{secondary.id}/edit",
            data={"name": "نحاسي", "hex_code": "#B87333"},
        )

        db_session.expire_all()
        assert "نحاسي" in db_session.get(Product, product.id).search_text


class TestRenamingAMeasurementRewritesItsProducts:

    def test_a_renamed_neck_size_reaches_the_index_both_ways(
        self, client, login, make_user, make_product, db_session
    ):
        neck = Size(name="28/410", kind=SIZE_KIND_NECK)
        db_session.add(neck)
        db_session.flush()

        product = make_product(name="غطاء")
        product.neck_size_id = neck.id
        db_session.flush()

        from utils.search_text import refresh_search_text
        refresh_search_text(product)
        db_session.commit()

        login(make_user(role="ADMIN"))
        client.post(f"/size/{neck.id}/edit", data={"name": "38/415", "kind": SIZE_KIND_NECK})

        db_session.expire_all()
        search_text = db_session.get(Product, product.id).search_text

        assert "38/415" in search_text
        # the bare number and "رقبة 38/415" are both searched for
        assert "رقبه" in search_text
        assert "28/410" not in search_text


# ------------------------------------------------------ a date means a local day

class TestADateFilterMeansALocalDay:

    def test_returns_none_for_nonsense(self):
        assert local_day_bounds("not-a-date") is None
        assert local_day_bounds("") is None
        assert local_day_bounds(None) is None

    def test_the_window_is_a_full_day(self):
        start, end = local_day_bounds("2026-07-15")
        assert (end - start).total_seconds() == 24 * 3600

    def test_summer_day_starts_three_hours_before_utc_midnight(self):
        # Nablus is UTC+3 in July, so the local day opens at 21:00 the
        # previous day in UTC
        start, _ = local_day_bounds("2026-07-15")
        assert start == datetime(2026, 7, 14, 21, 0)

    def test_winter_day_uses_the_winter_offset(self):
        # UTC+2 in December, so 22:00 the previous day
        start, _ = local_day_bounds("2026-12-15")
        assert start == datetime(2026, 12, 14, 22, 0)

    def test_the_bounds_are_naive_like_the_columns(self):
        start, end = local_day_bounds("2026-07-15")
        assert start.tzinfo is None and end.tzinfo is None

    @pytest.mark.parametrize("local_time,belongs_to", [
        ("2026-07-15 00:30", "2026-07-15"),   # just after local midnight
        ("2026-07-15 23:30", "2026-07-15"),   # just before the next one
    ])
    def test_an_early_movement_belongs_to_its_local_day(self, local_time, belongs_to):
        stored = local_to_utc(datetime.strptime(local_time, "%Y-%m-%d %H:%M"))
        start, end = local_day_bounds(belongs_to)

        assert start <= stored < end, \
            "حركة الساعة 00:30 بنابلس لازم تطلع بفلتر نفس اليوم"

    def test_the_old_naive_comparison_would_have_missed_it(self):
        # the shape of the bug, kept so the reason the helper exists is not
        # lost: midnight local is not midnight UTC
        stored = local_to_utc(datetime(2026, 7, 15, 0, 30))
        naive_midnight = datetime(2026, 7, 15, 0, 0)

        assert stored < naive_midnight
        assert local_day_bounds("2026-07-15")[0] <= stored


class TestTheDateFilterOnTheMovementsLog:

    def test_a_movement_made_early_in_the_local_day_is_found(
        self, client, login, make_user, make_product, make_location, db_session
    ):
        from models import InventoryTransaction

        product = make_product()
        location = make_location(product, quantity=10)

        db_session.add(InventoryTransaction(
            product_id=product.id,
            location_id=location.id,
            transaction_type="IN",
            quantity=5,
            quantity_before=5,
            quantity_after=10,
            created_at=local_to_utc(datetime(2026, 7, 15, 0, 30)),
        ))
        db_session.commit()

        login(make_user(role="ADMIN"))
        response = client.get("/transactions?date=2026-07-15")

        assert response.status_code == 200
        assert product.name.encode() in response.data, \
            "الحركة الساعة 00:30 كانت بتختفي من فلتر يومها"


# ------------------------------------------------- a shelf counted empty

class TestAnAdjustmentCanRecordZero:

    def _form(self, **overrides):
        form = {"transaction_type": "ADJUSTMENT", "location_id": "1",
                "quantity": "0", "notes": ""}
        form.update(overrides)
        return form

    def test_zero_is_accepted_for_an_adjustment(self):
        assert validate_transaction(self._form()).valid

    def test_a_negative_adjustment_is_still_refused(self):
        assert not validate_transaction(self._form(quantity="-1")).valid

    @pytest.mark.parametrize("kind", ["IN", "TRANSFER"])
    def test_zero_is_still_refused_for_a_real_movement(self, kind):
        assert not validate_transaction(self._form(transaction_type=kind)).valid

    def test_outbound_zero_is_still_refused(self):
        assert not validate_transaction(
            self._form(transaction_type="OUT", customer_id="1")
        ).valid

    def test_the_database_accepts_a_zero_adjustment(
        self, make_product, make_location, db_session
    ):
        from models import InventoryTransaction

        product = make_product()
        location = make_location(product, quantity=7)

        db_session.add(InventoryTransaction(
            product_id=product.id,
            location_id=location.id,
            transaction_type="ADJUSTMENT",
            quantity=0,
            quantity_before=7,
            quantity_after=0,
        ))
        db_session.commit()

        stored = db_session.execute(text(
            "SELECT quantity FROM inventory_transaction "
            "WHERE transaction_type = 'ADJUSTMENT'"
        )).scalar()

        assert stored == 0

    def test_the_database_still_refuses_a_zero_movement(
        self, make_product, make_location, db_session
    ):
        from models import InventoryTransaction

        product = make_product()
        location = make_location(product, quantity=7)

        db_session.add(InventoryTransaction(
            product_id=product.id,
            location_id=location.id,
            transaction_type="IN",
            quantity=0,
        ))

        with pytest.raises(Exception):
            db_session.commit()

        db_session.rollback()

    def test_a_stock_take_can_empty_a_shelf_through_the_route(
        self, client, login, make_user, make_product, make_location, db_session
    ):
        product = make_product()
        location = make_location(product, quantity=42)

        login(make_user(role="ADMIN"))
        response = client.post(
            f"/product/{product.id}/transaction/add",
            data={
                "transaction_type": "ADJUSTMENT",
                "location_id": str(location.id),
                "quantity": "0",
                "notes": "جردة: الرف فاضي",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        db_session.expire_all()
        assert db_session.get(type(location), location.id).quantity == 0, \
            "جردة لقيت الرف فاضي لازم تنكتب كتسوية، مش كإخراج وهمي"
