# -*- coding: utf-8 -*-
"""Response headers, and a Content-Security-Policy that only watches.

The headers in ALWAYS below cannot break a page: they refuse things the
application never does anyway. They go out on every response.

The policy is a different matter. A real CSP would refuse every inline
`<script>` and every `onclick=` in the templates -- 18 and 48 of them at the
time of writing -- and the first anyone would know is a button that stopped
working. So it is sent as Content-Security-Policy-Report-Only: the browser
checks every rule, reports what it would have blocked, and blocks nothing.
What comes back is the list of what has to move before the policy can be
enforced, taken from the pages people actually open rather than from a grep.

Switching it on afterwards is one word, REPORT_ONLY below.
"""

import json
import logging
import os
import re
from urllib.parse import urlsplit

from flask import request

logger = logging.getLogger(__name__)


# Send the policy as a report, or enforce it. Keep reporting until the log
# stops naming new things.
REPORT_ONLY = True

REPORT_PATH = "/csp-report"

# Bootstrap and its icon font, the only third party the pages load.
CDN = "https://cdn.jsdelivr.net"


ALWAYS = {
    # a response typed as text/plain must not be run as a script because it
    # happens to look like one
    "X-Content-Type-Options": "nosniff",

    # the warehouse has no reason to be inside anybody's frame, and this is
    # the half of frame-ancestors that older browsers understand
    "X-Frame-Options": "DENY",

    # a link out carries the origin, never the path: shelf ids and product
    # numbers are nobody else's business
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def image_origin():
    """Where product photos come from, so the policy can allow them."""

    return os.getenv("R2_PUBLIC_BASE", "").strip().rstrip("/")


def build_policy():
    images = ["'self'", "data:"]
    origin = image_origin()

    if origin:
        images.append(origin)

    directives = [
        ("default-src", "'self'"),

        # No 'unsafe-inline' on purpose, even while this only reports: the
        # whole point is to hear about every inline script there is.
        ("script-src", "'self' %s" % CDN),

        # style-src keeps 'unsafe-inline'. 50 style attributes is a day's
        # work for a far smaller prize -- a style attribute cannot run code,
        # and what it can do is already covered by the escaping that stopped
        # the one real injection this application had.
        ("style-src", "'self' %s 'unsafe-inline'" % CDN),

        ("font-src", "'self' %s" % CDN),
        ("img-src", " ".join(images)),
        ("connect-src", "'self'"),

        # a form that posts somewhere else is a phishing page wearing this
        # application's clothes
        ("form-action", "'self'"),
        ("base-uri", "'self'"),
        ("frame-ancestors", "'none'"),
        ("object-src", "'none'"),

        ("report-uri", REPORT_PATH),
    ]

    return "; ".join("%s %s" % (name, value) for name, value in directives)


# Every page reports the same handful of violations on every load, so the log
# would fill with one fact repeated. Each distinct one is written once, and
# the set is capped in case something unexpected keeps producing new ones.
_seen = set()
_SEEN_LIMIT = 500


# Every id in this application is a number, in its own path segment:
# /product/141, /category/3/delete.
_ID_SEGMENT = re.compile(r"/\d+(?=/|$)")


def _page(document_uri):
    """The template a violation came from, with nothing that varies by visit.

    A violation belongs to a template, so what identifies it has to as well,
    and the document-uri does not. /products and
    /products?sort=recent&category=4&page=2 render the same file; so do
    /product/141 and /product/229, with a different row in them. The host
    changes with the way in -- 192.168.x from inside the shop, the public
    address from outside. Keeping any of that turned a dozen templates into
    fifty-nine lines in the log, which is the opposite of the point, and would
    have spent _SEEN_LIMIT on the same handful of facts.
    """

    if not document_uri or document_uri == "?":
        return "?"

    path = urlsplit(document_uri).path or "/"

    return _ID_SEGMENT.sub("/<id>", path)[:200]


def _record(report):
    directive = report.get("effective-directive") or report.get("violated-directive", "?")
    blocked = (report.get("blocked-uri") or "?")[:120]
    page = _page(report.get("document-uri"))
    line = report.get("line-number", "")

    # The line number is not part of the key either, and cannot be: it is
    # counted in the rendered HTML, so one `<script>` sits at line 1886 on a
    # full product list and line 901 on a short one. It stays in the message,
    # where it points at roughly the right place, but it identifies nothing.
    key = (directive, blocked, page)

    if key in _seen:
        return False

    if len(_seen) < _SEEN_LIMIT:
        _seen.add(key)

    logger.warning(
        "CSP would have blocked %s on %s%s (%s)",
        blocked, page, (" line %s" % line) if line else "", directive
    )

    return True


def init_security_headers(app, csrf, limiter):

    policy = build_policy()
    header = (
        "Content-Security-Policy-Report-Only" if REPORT_ONLY
        else "Content-Security-Policy"
    )

    @app.after_request
    def add_security_headers(response):
        for name, value in ALWAYS.items():
            response.headers.setdefault(name, value)

        # The report endpoint answering with a policy of its own would have
        # the browser report on the report.
        if request.path != REPORT_PATH:
            response.headers.setdefault(header, policy)

        return response

    @app.route(REPORT_PATH, methods=["POST"])
    @csrf.exempt
    @limiter.limit("120 per hour")
    def csp_report():
        """Where the browser posts what the policy would have stopped.

        No login: the browser sends this on its own, without the session, and
        a violation on the login page is worth hearing about too. It reads
        the body and writes a log line; nothing it contains reaches a query,
        a template or a file name.
        """

        try:
            body = json.loads(request.get_data(as_text=True) or "{}")
        except ValueError:
            return "", 204

        report = body.get("csp-report") or body

        if isinstance(report, dict):
            _record(report)

        return "", 204

    return policy
