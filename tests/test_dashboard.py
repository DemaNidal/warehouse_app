# -*- coding: utf-8 -*-
"""The dashboard.

It was four stat cards of which two restated the table directly beneath
them and a third restated the navbar's bell, an unbounded list that could
push everything else off the screen, and three months of recorded movement
that never reached the page at all.

What is worth pinning down is the arithmetic the page now claims: that its
two stock numbers do not count the same products twice, that the list is
capped and says how many it left out, and that a movement is filed under
the day it happened in Nablus rather than the day it happened in UTC.
"""

import datetime
import re

import pytest

from utils.dashboard import TREND_DAYS, movement_trend, movements_since


@pytest.fixture()
def stocked(db_session, make_product, make_location):
    """Three products: one at zero, one under its minimum, one healthy."""
    from utils.search_text import refresh_search_text

    made = {}
    for key, name, quantity, minimum in [
        ("empty", "منتج فاضي", 0, 100),
        ("low", "منتج منخفض", 40, 100),
        ("fine", "منتج تمام", 900, 100),
    ]:
        product = make_product(name=name, minimum_stock=minimum)
        refresh_search_text(product)
        make_location(product, quantity=quantity, location="رف 4")
        made[key] = product

    db_session.commit()
    return made


def move(db_session, product, when, kind="IN", quantity=5):
    """A movement recorded at a given UTC moment."""
    from models import InventoryTransaction

    row = InventoryTransaction(
        product_id=product.id,
        location_id=product.locations[0].id,
        transaction_type=kind,
        quantity=quantity,
    )
    db_session.add(row)
    db_session.flush()
    row.created_at = when          # default= already fired, so set it after
    db_session.commit()
    return row


class TestWhoCanSeeIt:

    def test_requires_login(self, client):
        response = client.get("/dashboard")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_staff_are_turned_away(self, make_user, login):
        staff = login(make_user(username="staff", role="STAFF"))
        assert staff.get("/dashboard").status_code in (302, 403)

    def test_a_manager_gets_it(self, stocked, make_user, login):
        assert login(make_user()).get("/dashboard").status_code == 200


class TestTheTwoStockNumbers:
    """They used to overlap: "تحتاج متابعة" counted the products that "نفد"
    had already counted, so the cards added up to more than the list."""

    def body(self, stocked, make_user, login):
        return login(make_user()).get("/dashboard").get_data(as_text=True)

    def test_they_do_not_count_the_same_product_twice(
        self, stocked, make_user, login
    ):
        body = self.body(stocked, make_user, login)

        cards = re.findall(
            r'<span class="n">(\d+)</span>\s*<span class="t">([^<]+)</span>',
            body,
        )
        numbers = {label.strip(): int(value) for value, label in cards}

        assert numbers["نفد المخزون"] == 1
        assert numbers["منخفض"] == 1

    def test_the_link_on_each_card_filters_to_what_it_counts(
        self, stocked, make_user, login
    ):
        body = self.body(stocked, make_user, login)

        assert "stock=critical" in body
        assert "stock=low" in body
        assert "sort=quantity_asc" in body

    def test_the_healthy_product_is_in_neither(
        self, stocked, make_user, login
    ):
        body = self.body(stocked, make_user, login)
        assert "منتج تمام" not in body


class TestTheList:

    def test_it_is_capped(self, db_session, make_product, make_location,
                          make_user, login):
        from utils.search_text import refresh_search_text

        for n in range(14):
            product = make_product(name=f"ناقص {n}", minimum_stock=100)
            refresh_search_text(product)
            make_location(product, quantity=n, location="رف 1")
        db_session.commit()

        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert len(re.findall(r"<tr onclick", body)) == 8

    def test_it_says_how_many_it_left_out(
        self, db_session, make_product, make_location, make_user, login
    ):
        from utils.search_text import refresh_search_text

        for n in range(14):
            product = make_product(name=f"ناقص {n}", minimum_stock=100)
            refresh_search_text(product)
            make_location(product, quantity=n, location="رف 1")
        db_session.commit()

        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert "و6 غيرهم تحت الحد" in body

    def test_the_emptiest_come_first(self, stocked, make_user, login):
        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert body.index("منتج فاضي") < body.index("منتج منخفض")

    def test_a_healthy_catalogue_says_so(self, make_user, login):
        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert "كل المنتجات فوق الحد الأدنى" in body


class TestTheTrend:

    def test_it_covers_the_window_oldest_first(self, app):
        with app.app_context():
            trend = movement_trend()

        assert len(trend) == TREND_DAYS
        assert [day["date"] for day in trend] == sorted(
            day["date"] for day in trend
        )

    def test_today_is_the_last_bar(self, app):
        from utils.clock import to_local, utcnow

        with app.app_context():
            trend = movement_trend()
            assert trend[-1]["date"] == to_local(utcnow()).date()

    def test_a_movement_lands_on_its_day(self, app, db_session, stocked):
        from utils.clock import to_local, utcnow

        today = to_local(utcnow()).date()
        move(db_session, stocked["fine"], utcnow(), kind="IN")

        with app.app_context():
            trend = {day["date"]: day for day in movement_trend()}

        assert trend[today]["incoming"] >= 1

    def test_outgoing_and_transfers_share_a_bar(self, app, db_session, stocked):
        """On a chart of activity, what left and what moved belong together;
        what matters is the direction against arrivals."""
        from utils.clock import to_local, utcnow

        today = to_local(utcnow()).date()
        move(db_session, stocked["fine"], utcnow(), kind="OUT")
        move(db_session, stocked["fine"], utcnow(), kind="TRANSFER")

        with app.app_context():
            trend = {day["date"]: day for day in movement_trend()}

        assert trend[today]["outgoing"] == 2
        assert trend[today]["incoming"] == 0

    def test_a_movement_before_the_window_is_not_counted(
        self, app, db_session, stocked
    ):
        from utils.clock import utcnow

        move(db_session, stocked["fine"],
             utcnow() - datetime.timedelta(days=TREND_DAYS + 5))

        with app.app_context():
            trend = movement_trend()

        assert sum(day["total"] for day in trend) == 0

    def test_the_day_is_the_local_one_not_utc(self, app, db_session, stocked):
        """Palestine runs two or three hours ahead, so 01:30 this morning in
        Nablus was still yesterday evening in UTC. Grouping on the stored
        value would file it under yesterday's bar — the same confusion that
        put 927 rows an hour out once already.

        01:30 rather than 23:30 on purpose: the late hour has not happened
        yet when the suite runs in the morning, and a guard that skips half
        the day is not a guard.
        """
        from utils.clock import LOCAL_TZ, to_local, utcnow

        local_today = to_local(utcnow()).date()

        early = datetime.datetime.combine(
            local_today, datetime.time(1, 30), tzinfo=LOCAL_TZ
        )
        as_utc = early.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        # the point of the test: UTC disagrees about which day this is
        assert as_utc.date() < local_today, (
            "local time is not ahead of UTC, so this proves nothing"
        )

        move(db_session, stocked["fine"], as_utc)

        with app.app_context():
            trend = {day["date"]: day for day in movement_trend()}

        assert trend[local_today]["incoming"] >= 1
        assert trend[as_utc.date()]["incoming"] == 0

    def test_bars_are_drawn_against_the_busiest_day(
        self, app, db_session, stocked
    ):
        from utils.clock import utcnow

        for _ in range(4):
            move(db_session, stocked["fine"], utcnow())
        move(db_session, stocked["fine"],
             utcnow() - datetime.timedelta(days=2))

        with app.app_context():
            trend = movement_trend()

        busiest = max(trend, key=lambda day: day["total"])
        assert busiest["in_height"] + busiest["out_height"] == 100
        assert all(
            day["in_height"] + day["out_height"] <= 100 for day in trend
        )

    def test_a_quiet_day_draws_a_flat_line_not_a_gap(
        self, stocked, make_user, login
    ):
        """An empty column reads as missing data rather than a quiet day."""
        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert 'class="bar none"' in body

    def test_every_bar_names_its_day_and_counts(
        self, stocked, make_user, login
    ):
        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        titles = re.findall(r'<div class="dash-trend-day"\s*\n?\s*title="([^"]+)"', body)
        assert len(titles) == TREND_DAYS
        assert all("إدخال" in title and "إخراج" in title for title in titles)


class TestMovementsSince:

    def test_it_counts_the_recent_ones(self, app, db_session, stocked):
        from utils.clock import utcnow

        move(db_session, stocked["fine"], utcnow())
        move(db_session, stocked["fine"],
             utcnow() - datetime.timedelta(days=3))
        move(db_session, stocked["fine"],
             utcnow() - datetime.timedelta(days=20))

        with app.app_context():
            assert movements_since(7) == 2


class TestWhatWasRemoved:

    def test_the_banner_is_gone(self, stocked, make_user, login):
        """Three lines telling the only person who opens this page what this
        page is, plus three buttons that are all in the navbar."""
        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert "dashboard-hero" not in body
        assert "نظرة سريعة على المخزون" not in body

    def test_the_full_battery_no_longer_means_empty_stock(
        self, stocked, make_user, login
    ):
        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert "bi-battery-full" not in body

    def test_the_notification_count_is_not_repeated(
        self, stocked, make_user, login
    ):
        """The navbar bell already carries it, from the context processor."""
        body = login(make_user()).get("/dashboard").get_data(as_text=True)
        assert "إشعارات جديدة" not in body
