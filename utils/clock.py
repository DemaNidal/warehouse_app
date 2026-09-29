# -*- coding: utf-8 -*-
"""One clock for the whole system.

Timestamps used to come from two places that disagreed. Columns defaulting to
`db.func.now()` took PostgreSQL's clock, which runs on `TimeZone = GMT`;
columns defaulting to `datetime.now` took the machine's clock, three hours
ahead in Palestine. A product created and never touched showed `created_at`
11:12 and `updated_at` 14:12 — the same instant, written twice.

So: **everything is stored in UTC, and converted to local time only when it is
shown.** Storing local time would have to be revisited the moment the
application runs on a server in another country, which it is about to.

The columns are `timestamp without time zone`, so what is stored is naive — the
convention is that a naive datetime anywhere in this system is UTC.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Where the warehouse is. Only display uses it; nothing is stored in it.
LOCAL_TZ = ZoneInfo("Asia/Hebron")

UTC = timezone.utc


def utcnow():
    """The current moment in UTC, naive — the one default every column uses."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_local(value):
    """A stored UTC timestamp as local time, for display.

    Returns None unchanged so templates can hand it a column that may be empty.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(LOCAL_TZ)


def local_to_utc(value):
    """A naive local timestamp read as UTC — used to correct rows written
    before this module existed.

    Goes through the zone rather than subtracting a fixed offset, because
    Palestine moves on and off summer time: the same wall-clock hour is +03 in
    August and +02 in December.
    """
    if value is None:
        return None

    return value.replace(tzinfo=LOCAL_TZ).astimezone(UTC).replace(tzinfo=None)
