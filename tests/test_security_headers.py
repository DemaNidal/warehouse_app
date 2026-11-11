# -*- coding: utf-8 -*-
"""The headers every response carries, and the policy that only watches.

A real Content-Security-Policy would refuse every inline script and every
onclick in the templates, and the first anyone would know is a button that
stopped working. So it goes out as Report-Only first: the browser checks it,
tells us what it would have stopped, and stops nothing. These cover the part
that is already real — the headers, the shape of the policy, and the endpoint
the browser reports to.
"""

import json

import pytest

from utils.security_headers import ALWAYS, REPORT_ONLY, build_policy


class TestTheHeadersThatCannotBreakAnything:

    @pytest.mark.parametrize("header,value", sorted(ALWAYS.items()))
    def test_every_response_carries_it(self, client, header, value):
        assert client.get("/login").headers.get(header) == value

    def test_a_page_behind_the_login_carries_them_too(self, client, login, make_user):
        login(make_user(role="ADMIN"))

        response = client.get("/products")

        for header, value in ALWAYS.items():
            assert response.headers.get(header) == value

    def test_they_do_not_disturb_the_no_cache_rule(self, client, login, make_user):
        login(make_user(role="ADMIN"))

        response = client.get("/products")

        assert "no-store" in response.headers.get("Cache-Control", "")


class TestThePolicyWatchesRatherThanBlocks:

    def test_it_is_sent_as_report_only(self, client):
        response = client.get("/login")

        assert "Content-Security-Policy-Report-Only" in response.headers
        assert "Content-Security-Policy" not in response.headers, \
            "an enforcing policy would break every inline script in the templates"

    def test_report_only_is_still_the_setting(self):
        # a reminder in the suite: flipping this is a deliberate act, after
        # the log has stopped naming new things
        assert REPORT_ONLY is True


class TestWhatThePolicyActuallySays:

    def test_inline_script_is_not_allowed_even_while_reporting(self):
        directives = dict(
            part.split(" ", 1) for part in build_policy().split("; ")
        )

        assert "'unsafe-inline'" not in directives["script-src"], \
            "allowing inline script would report nothing, which is the point"
        assert "'unsafe-eval'" not in directives["script-src"]

    def test_the_things_a_page_really_needs_are_allowed(self):
        directives = dict(
            part.split(" ", 1) for part in build_policy().split("; ")
        )

        # bootstrap and its icon font
        assert "https://cdn.jsdelivr.net" in directives["script-src"]
        assert "https://cdn.jsdelivr.net" in directives["style-src"]
        assert "https://cdn.jsdelivr.net" in directives["font-src"]

        # style attributes stay allowed on purpose
        assert "'unsafe-inline'" in directives["style-src"]

    def test_the_dangerous_ones_are_shut(self):
        directives = dict(
            part.split(" ", 1) for part in build_policy().split("; ")
        )

        assert directives["frame-ancestors"] == "'none'"
        assert directives["object-src"] == "'none'"
        assert directives["form-action"] == "'self'"
        assert directives["base-uri"] == "'self'"

    def test_product_photos_are_allowed_from_their_bucket(self, monkeypatch):
        monkeypatch.setenv("R2_PUBLIC_BASE", "https://pictures.example.com/")

        directives = dict(
            part.split(" ", 1) for part in build_policy().split("; ")
        )

        assert "https://pictures.example.com" in directives["img-src"], \
            "without this every product photo reports as a violation"

    def test_it_survives_having_no_bucket_configured(self, monkeypatch):
        monkeypatch.setenv("R2_PUBLIC_BASE", "")

        directives = dict(
            part.split(" ", 1) for part in build_policy().split("; ")
        )

        assert directives["img-src"] == "'self' data:"


class TestTheReportEndpoint:

    def test_a_browser_can_post_a_report_without_signing_in(self, client):
        response = client.post(
            "/csp-report",
            data=json.dumps({"csp-report": {
                "document-uri": "http://localhost/products",
                "violated-directive": "script-src",
                "blocked-uri": "inline",
                "line-number": 42,
            }}),
            content_type="application/csp-report",
        )

        assert response.status_code == 204

    def test_it_does_not_report_on_itself(self, client):
        response = client.post(
            "/csp-report", data="{}", content_type="application/csp-report")

        assert "Content-Security-Policy-Report-Only" not in response.headers

    def test_rubbish_does_not_raise(self, client):
        response = client.post(
            "/csp-report", data="not json at all",
            content_type="application/csp-report")

        assert response.status_code == 204

    def test_a_report_is_written_once_not_on_every_page_load(self, client, monkeypatch):
        from utils import security_headers

        security_headers._seen.clear()

        # Watching the logger directly rather than through caplog: what
        # matters is that the same violation is written once however many
        # times the browser sends it, and this says exactly that.
        written = []
        monkeypatch.setattr(
            security_headers.logger, "warning",
            lambda *args, **kwargs: written.append(args[0])
        )

        body = json.dumps({"csp-report": {
            "document-uri": "http://localhost/dashboard",
            "violated-directive": "script-src",
            "blocked-uri": "inline",
            "line-number": 7,
        }})

        for _ in range(5):
            client.post("/csp-report", data=body,
                        content_type="application/csp-report")

        assert len(written) == 1,             "the same violation on every page load would bury the new ones"

    def test_a_different_violation_is_written_too(self, client, monkeypatch):
        from utils import security_headers

        security_headers._seen.clear()

        written = []
        monkeypatch.setattr(
            security_headers.logger, "warning",
            lambda *args, **kwargs: written.append(args[0])
        )

        for line in (7, 31):
            client.post("/csp-report", data=json.dumps({"csp-report": {
                "document-uri": "http://localhost/dashboard",
                "violated-directive": "script-src",
                "blocked-uri": "inline",
                "line-number": line,
            }}), content_type="application/csp-report")

        assert len(written) == 2,             "deduplicating must not swallow a violation nobody has seen yet"
