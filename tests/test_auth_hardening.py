# -*- coding: utf-8 -*-
"""Signing in, and the two walls people hit while doing it.

Three defects, all met in ordinary use rather than found by reading:

  * the rate limit covered the whole route, so opening the login page five
    times — a refresh, a mistyped password, the back button — locked the door
    for a minute behind an English error page;
  * a CSRF failure (a tab left open, a browser restarted) showed
    "Bad Request: The CSRF session token is missing" and no way forward;
  * PERMANENT_SESSION_LIFETIME was set to eight hours and had no effect,
    because the session was never marked permanent — so everyone signed in
    again each morning.

The rate limit is disabled for the rest of the suite (see conftest), so these
turn it back on deliberately.
"""

import re

import pytest


@pytest.fixture()
def rate_limited(app):
    """Run with the limiter live, and reset its counters afterwards."""
    from extensions import limiter

    app.config["RATELIMIT_ENABLED"] = True
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False
    app.config["RATELIMIT_ENABLED"] = False


@pytest.fixture()
def csrf_on(app):
    """CSRF is off for the rest of the suite; these tests are about it."""
    app.config["WTF_CSRF_ENABLED"] = True
    yield
    app.config["WTF_CSRF_ENABLED"] = False


@pytest.fixture()
def account(make_user):
    return make_user(username="dema", password="a-real-password")


class TestOpeningTheLoginPage:

    def test_is_not_rate_limited(self, client, rate_limited):
        """The defect itself: viewing a page is not an attempt."""
        codes = [client.get("/login").status_code for _ in range(12)]
        assert set(codes) == {200}


class TestFailedAttempts:

    def test_are_rate_limited(self, client, rate_limited):
        codes = [
            client.post("/login", data={
                "username": "لا_يوجد", "password": "wrong-password",
            }).status_code
            for _ in range(14)
        ]
        assert 429 in codes, "guessing is not throttled"

    def test_allow_a_reasonable_number_first(self, client, rate_limited):
        # someone mistyping their own password a few times must not be locked out
        codes = [
            client.post("/login", data={
                "username": "dema", "password": "wrong",
            }).status_code
            for _ in range(5)
        ]
        assert 429 not in codes

    def test_the_block_page_is_arabic_and_offers_a_way_back(
        self, client, rate_limited
    ):
        for _ in range(14):
            response = client.post("/login", data={
                "username": "x", "password": "y",
            })

        body = response.get_data(as_text=True)
        assert response.status_code == 429
        assert "محاولات كثيرة" in body
        assert "رجوع لصفحة الدخول" in body
        assert "Too Many Requests" not in body


class TestExpiredPage:

    def test_a_missing_csrf_token_explains_itself(self, client, csrf_on):
        response = client.post("/login", data={
            "username": "x", "password": "y", "csrf_token": "stale",
        })
        body = response.get_data(as_text=True)

        assert "انتهت صلاحية الصفحة" in body
        assert "CSRF session token is missing" not in body

    def test_it_offers_the_page_again(self, client, csrf_on):
        response = client.post("/login", data={"csrf_token": "stale"})
        assert "افتحي الصفحة من جديد" in response.get_data(as_text=True)

    def test_it_renders_for_a_signed_out_visitor(self, client, csrf_on):
        """It extends auth_base for this reason — base.html needs a user and
        would raise, turning a friendly page into a 500."""
        response = client.post("/login", data={"csrf_token": "stale"})
        assert response.status_code == 400


class TestSessionLifetime:

    def test_signing_in_sets_a_lasting_cookie(self, client, account):
        """Without `session.permanent`, the eight-hour setting does nothing and
        the cookie dies when the browser closes."""
        response = client.post("/login", data={
            "username": "dema", "password": "a-real-password",
        })
        assert response.status_code == 302

        cookie = response.headers.get("Set-Cookie", "")
        assert "Expires=" in cookie or "Max-Age=" in cookie, (
            "session cookie is still a browser-session cookie"
        )

    def test_the_cookie_lasts_about_eight_hours(self, client, account):
        response = client.post("/login", data={
            "username": "dema", "password": "a-real-password",
        })

        cookie = response.headers.get("Set-Cookie", "")
        match = re.search(r"Max-Age=(\d+)", cookie)
        if match:
            assert 7 * 3600 <= int(match.group(1)) <= 9 * 3600

    def test_the_cookie_stays_protected(self, client, account):
        response = client.post("/login", data={
            "username": "dema", "password": "a-real-password",
        })
        cookie = response.headers.get("Set-Cookie", "")

        # a longer-lived cookie must not be a less careful one
        assert "HttpOnly" in cookie
        assert "SameSite=Lax" in cookie

    def test_a_wrong_password_sets_no_lasting_session(self, client, account):
        # the form re-renders with the error rather than redirecting
        response = client.post("/login", data={
            "username": "dema", "password": "wrong",
        })
        assert response.status_code == 200
        assert "بيانات الدخول غير صحيحة" in response.get_data(as_text=True)

        cookie = response.headers.get("Set-Cookie", "")
        assert "Max-Age=" not in cookie, "a failed attempt left a lasting session"


class TestChangingAPasswordClosesTheOtherSessions:
    """Changing a password used to leave every session it had opened running.

    Flask-Login puts the user's id in the cookie and nothing else, so a
    browser already signed in stayed signed in for the rest of the eight
    hours — the new password simply did not concern it. Somebody changing
    their password because they think another person is inside their account
    was not achieving the one thing they were trying to achieve.

    The cookie carries the password's version now. These cover both halves:
    the other session must end, and the one doing the changing must not.
    """

    def test_another_session_is_closed(self, app, make_user, db_session):
        user = make_user(username="hana", role="STORE_MANAGER")
        db_session.commit()

        elsewhere = app.test_client()
        with elsewhere.session_transaction() as session:
            session["_user_id"] = user.get_id()
            session["_fresh"] = True

        assert elsewhere.get("/products").status_code == 200, \
            "the second browser should start out signed in"

        user.set_password("a-different-password")
        db_session.commit()

        # db_session holds one app context open for the whole test and
        # Flask-Login caches the loaded user on `g`, which lives there — so
        # without this the second request answers from the cache and never
        # consults the loader. Each real request gets a context of its own.
        from flask import g
        for cached in ("_login_user", "_cached_user"):
            g.pop(cached, None)

        response = elsewhere.get("/products")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"], \
            "a session opened with the old password must not survive it"

    def test_the_browser_that_changed_it_stays(self, client, login, make_user, db_session):
        user = make_user(username="rami", role="STORE_MANAGER", password="old-password-here")
        db_session.commit()
        login(user)

        response = client.post("/profile/change-password", data={
            "current_password": "old-password-here",
            "new_password": "brand-new-password",
            "confirm_password": "brand-new-password",
        }, follow_redirects=False)

        assert response.status_code == 302

        assert client.get("/products").status_code == 200, \
            "the person who chose the new password should not be thrown out"

    def test_a_cookie_from_before_this_existed_is_refused(self, app, make_user, db_session):
        # sessions already open when this is deployed hold a bare id, and
        # there is no way to tell whether the password changed since
        user = make_user(username="older", role="STORE_MANAGER")
        db_session.commit()

        stale = app.test_client()
        with stale.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True

        from flask import g
        for cached in ("_login_user", "_cached_user"):
            g.pop(cached, None)

        response = stale.get("/products")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_the_version_moves_with_every_change(self, make_user, db_session):
        user = make_user(username="counter")
        db_session.commit()

        first = user.auth_version
        user.set_password("second-password")
        db_session.commit()
        second = user.auth_version

        assert second == first + 1
        assert user.get_id() == "%s-%s" % (user.id, second)
