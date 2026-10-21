# -*- coding: utf-8 -*-
"""Telling people about stock requests.

None of this reached anyone. A request was saved and only the person who
made it saw a flash message, so a manager learned of it by opening the
requests page on the off chance. Approving told nobody — although the
notifications page has carried an "OUT_APPROVED" branch, icon and wording
and all, the whole time, waiting for a notification that no code created.
Rejecting was the one path that notified, and across twenty-six requests it
had never been taken, so in practice not one notification about a request
had ever been sent.
"""

import pytest

from models import Notification


@pytest.fixture()
def product(db_session, make_product, make_location):
    from utils.search_text import refresh_search_text

    made = make_product(name="غطاء للطلب", minimum_stock=10)
    refresh_search_text(made)
    make_location(made, quantity=5000, location="رف 6")
    db_session.commit()
    return made


@pytest.fixture()
def people(make_user):
    return {
        "boss": make_user(username="المديرة", role="ADMIN"),
        "manager": make_user(username="أمين المستودع", role="STORE_MANAGER"),
        "clerk": make_user(username="موظف", role="STAFF"),
        "asker": make_user(username="طالب", role="STORE_MANAGER"),
    }


def ask_for_stock(client, product, quantity=100, customer_id=None):
    """A staff member asks for stock to leave."""
    from models import Customer, db

    if customer_id is None:
        customer = Customer.query.first()
        if customer is None:
            customer = Customer(name="زبون اختبار")
            db.session.add(customer)
            db.session.commit()
        customer_id = customer.id

    return client.post(
        f"/product/{product.id}/transaction/add",
        data={
            "transaction_type": "OUT",
            "location_id": product.locations[0].id,
            "quantity": str(quantity),
            "customer_id": str(customer_id),
            "notes": "",
        },
        follow_redirects=True,
    )


def waiting_for(user, kind=None):
    query = Notification.query.filter_by(user_id=user.id)
    if kind:
        query = query.filter_by(type=kind)
    return query.all()


class TestANewRequest:

    def test_it_reaches_the_managers(self, db_session, product, people, login):
        from models import StockRequest

        clerk = login(people["asker"])
        ask_for_stock(clerk, product)

        assert StockRequest.query.count() == 1
        assert waiting_for(people["boss"], "OUT_REQUESTED")

    def test_only_those_who_can_decide_are_told(
        self, db_session, product, people, login
    ):
        """Approving is admin-only, so telling a store manager about a
        request they cannot act on is noise — and staff cannot even see it."""
        asker = login(people["asker"])
        ask_for_stock(asker, product)

        assert not waiting_for(people["clerk"])
        assert not waiting_for(people["manager"], "OUT_REQUESTED")
        assert waiting_for(people["boss"], "OUT_REQUESTED")

    def test_it_points_at_the_requests_page(
        self, db_session, product, people, login
    ):
        clerk = login(people["asker"])
        ask_for_stock(clerk, product)

        notice = waiting_for(people["boss"], "OUT_REQUESTED")[0]
        assert notice.target_url == "/stock-requests"

    def test_an_admin_is_not_alerted_about_their_own_request(
        self, app, db_session, product, people, make_user, login
    ):
        """Checked at the helper, because no route reaches it: admins take
        stock out directly and never create a request. The exclusion stays
        for the day that changes — being alerted about your own request is
        noise, and with one admin it would be the only alert sent."""
        from models import StockRequest
        from utils.notifications import notify_managers_of_request

        second = make_user(username="مديرة تانية", role="ADMIN")

        asker = login(people["asker"])
        ask_for_stock(asker, product)
        stock_request = StockRequest.query.one()

        Notification.query.delete()
        stock_request.requested_by = people["boss"].id
        db_session.commit()

        # the helper builds its link with url_for, so it wants a request
        # context — it is only ever called from inside one
        with app.test_request_context():
            told = notify_managers_of_request(stock_request)
        db_session.commit()

        assert told == 1
        assert not waiting_for(people["boss"], "OUT_REQUESTED")
        assert waiting_for(second, "OUT_REQUESTED")

    def test_nothing_is_left_behind_when_the_request_fails(
        self, db_session, product, people, login
    ):
        """More than the shelf holds: no request, so no notification."""
        from models import StockRequest

        clerk = login(people["asker"])
        ask_for_stock(clerk, product, quantity=999_999)

        assert StockRequest.query.count() == 0
        assert not waiting_for(people["boss"], "OUT_REQUESTED")


class TestTheDecision:

    def request_id(self, product, people, login):
        from models import StockRequest

        clerk = login(people["asker"])
        ask_for_stock(clerk, product)
        return StockRequest.query.one().id

    def test_approving_tells_the_person_who_asked(
        self, db_session, product, people, login
    ):
        request_id = self.request_id(product, people, login)

        boss = login(people["boss"])
        boss.post(f"/stock-request/{request_id}/approve")

        notices = waiting_for(people["asker"], "OUT_APPROVED")
        assert len(notices) == 1
        assert notices[0].product_id == product.id

    def test_rejecting_tells_them_too(
        self, db_session, product, people, login
    ):
        request_id = self.request_id(product, people, login)

        boss = login(people["boss"])
        boss.post(f"/stock-request/{request_id}/reject")

        assert waiting_for(people["asker"], "OUT_REJECTED")

    def test_the_notice_opens_the_product(
        self, db_session, product, people, login
    ):
        request_id = self.request_id(product, people, login)

        boss = login(people["boss"])
        boss.post(f"/stock-request/{request_id}/approve")

        notice = waiting_for(people["asker"], "OUT_APPROVED")[0]
        assert notice.target_url == f"/product/{product.id}"

    def test_an_admin_taking_stock_out_makes_no_request_at_all(
        self, db_session, product, people, login
    ):
        """Admins bypass the request flow entirely — they remove stock
        directly — so there is nothing to approve and nobody to tell."""
        from models import StockRequest

        boss = login(people["boss"])
        ask_for_stock(boss, product)

        assert StockRequest.query.count() == 0
        assert not Notification.query.filter(
            Notification.type.in_(["OUT_REQUESTED", "OUT_APPROVED"])
        ).all()

    def test_nobody_is_told_about_their_own_decision(
        self, app, db_session, product, people, login
    ):
        """Guarded at the helper rather than through a route: an admin
        cannot reach this, because admins never create requests. The guard
        stays because the day one of them can, an alert telling someone
        what they just did themselves is noise."""
        from models import StockRequest
        from utils.notifications import notify_requester

        asker = login(people["asker"])
        ask_for_stock(asker, product)
        stock_request = StockRequest.query.one()

        stock_request.approved_by = stock_request.requested_by
        db_session.commit()

        with app.test_request_context():
            assert notify_requester(stock_request, approved=True) is False
        assert not waiting_for(people["asker"], "OUT_APPROVED")

    def test_a_refused_approval_notifies_nobody(
        self, db_session, product, people, login
    ):
        """Approving twice: the second is turned away, and must not send a
        second notice saying it went through."""
        request_id = self.request_id(product, people, login)

        boss = login(people["boss"])
        boss.post(f"/stock-request/{request_id}/approve")
        boss.post(f"/stock-request/{request_id}/approve")

        assert len(waiting_for(people["asker"], "OUT_APPROVED")) == 1


class TestWhatThePageCanShow:

    def test_the_page_renders_the_types_that_are_now_created(
        self, db_session, product, people, login
    ):
        """OUT_APPROVED had a branch in the template and no producer."""
        request_id = TestTheDecision().request_id(product, people, login)

        boss = login(people["boss"])
        boss.post(f"/stock-request/{request_id}/approve")

        clerk = login(people["asker"])
        body = clerk.get("/notifications").get_data(as_text=True)

        assert "تمت الموافقة على طلب الإخراج" in body
        assert "غطاء للطلب" in body

    def test_the_bell_counts_it(self, db_session, product, people, login):
        clerk = login(people["asker"])
        ask_for_stock(clerk, product)

        boss = login(people["boss"])
        body = boss.get("/products").get_data(as_text=True)

        assert "badge-dot" in body
