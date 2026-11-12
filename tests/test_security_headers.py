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


@pytest.fixture()
def written(monkeypatch):
    """Every line the recorder wrote, formatted, in order.

    Watching the logger directly rather than through caplog: what matters is
    which violations reach the log at all, and this says exactly that.
    """

    from utils import security_headers

    security_headers._seen.clear()

    lines = []

    def capture(*args, **kwargs):
        lines.append(args[0] % args[1:] if len(args) > 1 else args[0])

    monkeypatch.setattr(security_headers.logger, "warning", capture)

    return lines


@pytest.fixture()
def report(client):
    """Post a violation the way a browser does."""

    def send(document, directive="script-src-elem", blocked="inline", line=None):
        violation = {
            "document-uri": document,
            "effective-directive": directive,
            "blocked-uri": blocked,
        }

        if line is not None:
            violation["line-number"] = line

        return client.post(
            "/csp-report",
            data=json.dumps({"csp-report": violation}),
            content_type="application/csp-report",
        )

    return send


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


class TestTheLogStaysReadable:
    """What the log is for is a list of the templates that have to change.

    Repeated on every page load, or once per filter and once per line number,
    it is a list of nothing. These say what counts as the same violation, and
    they exist because the first version of this got it wrong in production:
    six pages arrived as fifty-nine lines.
    """

    def test_a_violation_is_written_once_not_on_every_page_load(self, report, written):
        for _ in range(5):
            report("http://localhost/dashboard", line=7)

        assert len(written) == 1,             "the same violation on every page load would bury the new ones"

    def test_the_same_page_under_a_filter_is_not_a_new_violation(self, report, written):
        report("http://localhost/products", line=1886)
        report("http://localhost/products?sort=recent&category=4&page=2", line=901)
        report("http://localhost/products?sort=recent&category=5", line=1463)

        assert len(written) == 1,             "one template reported once per filter is a log nobody can read"

    def test_a_line_number_that_moved_is_not_a_new_violation(self, report, written):
        # the number is counted in the rendered page, so a shorter product
        # list moves the same script up a thousand lines
        report("http://localhost/products", line=1886)
        report("http://localhost/products", line=901)

        assert len(written) == 1

    def test_the_way_in_does_not_make_it_new(self, report, written):
        report("http://192.168.0.5:5000/dashboard", line=1019)
        report("http://213.6.239.66:5000/dashboard", line=1019)
        report("http://localhost:5000/dashboard", line=1019)

        assert len(written) == 1,             "the same page from the shop and from outside is still one page"

    def test_the_same_template_with_another_product_in_it_is_not_new(self, report, written):
        report("http://localhost/product/141", line=1046)
        report("http://localhost/product/229", line=846)
        report("http://localhost/product/56", line=846)

        assert len(written) == 1,             "one product page per product is a list of the catalogue, not of the work"

    def test_the_id_is_not_dropped_from_the_path_altogether(self, report, written):
        report("http://localhost/product/141")
        report("http://localhost/products")

        assert len(written) == 2
        pages = " ".join(written)
        assert "/product/<id>" in pages
        assert "/products" in pages

    def test_a_different_page_is_written_too(self, report, written):
        report("http://localhost/dashboard")
        report("http://localhost/products")

        assert len(written) == 2,             "deduplicating must not swallow a violation nobody has seen yet"

    def test_both_kinds_of_inline_on_one_page_are_written(self, report, written):
        # an inline <script> and an onclick= are two separate pieces of work
        report("http://localhost/dashboard", directive="script-src-elem")
        report("http://localhost/dashboard", directive="script-src-attr")

        assert len(written) == 2

    def test_the_line_number_is_still_in_the_message(self, report, written):
        report("http://localhost/products?sort=recent", line=1886)

        assert "line 1886" in written[0]
        assert "/products" in written[0]
        assert "sort=recent" not in written[0],             "the query says nothing about which template has to change"

    def test_a_report_without_a_page_does_not_land_on_the_root(self, report, written):
        report("")
        report("http://localhost/")

        assert len(written) == 2,             "a report that names no page is not a report about the home page"
