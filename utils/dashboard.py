# -*- coding: utf-8 -*-
"""What the dashboard needs that is not a plain count.

The page used to be entirely a snapshot: how many products, how many low,
how many unread. Three months of recorded movement never reached the screen,
so the one question a warehouse asks every morning — did anything move, and
which way — had no answer on the page that exists to answer it.
"""

import datetime
from collections import Counter

from models import InventoryTransaction, db
from utils.clock import to_local, utcnow

TREND_DAYS = 30


def movement_trend(days=TREND_DAYS):
    """One entry per day, oldest first, with heights ready for the bars.

    Bucketed in Python rather than grouped in SQL because the rows are
    stored in UTC and the day they belong to is the local one: a movement
    at 22:30 UTC in summer is the next day in Nablus, and grouping on the
    stored value would file it under the wrong bar. The window is small —
    a few hundred rows — so the cost of being right is nothing.
    """
    today = to_local(utcnow()).date()
    first = today - datetime.timedelta(days=days - 1)

    # a day either side of the window, so the timezone shift cannot drop a
    # movement that belongs to the first or last bar
    cutoff = utcnow() - datetime.timedelta(days=days + 1)

    rows = (
        db.session.query(
            InventoryTransaction.created_at,
            InventoryTransaction.transaction_type,
        )
        .filter(InventoryTransaction.created_at >= cutoff)
        .all()
    )

    incoming, outgoing = Counter(), Counter()
    for created_at, kind in rows:
        when = to_local(created_at).date()
        if when < first or when > today:
            continue
        if kind == "IN":
            incoming[when] += 1
        else:
            # everything that is not an arrival leaves or moves, and on a
            # bar chart of activity those belong together
            outgoing[when] += 1

    series = [first + datetime.timedelta(days=i) for i in range(days)]
    peak = max(
        (incoming[day] + outgoing[day] for day in series), default=0
    ) or 1

    return [
        {
            "date": day,
            "label": day.strftime("%m-%d"),
            "incoming": incoming[day],
            "outgoing": outgoing[day],
            "total": incoming[day] + outgoing[day],
            "in_height": round(100 * incoming[day] / peak, 2),
            "out_height": round(100 * outgoing[day] / peak, 2),
        }
        for day in series
    ]


def movements_since(days=7):
    """How many movements were recorded in the last `days` local days."""
    today = to_local(utcnow()).date()
    first = today - datetime.timedelta(days=days - 1)
    cutoff = utcnow() - datetime.timedelta(days=days + 1)

    rows = (
        db.session.query(InventoryTransaction.created_at)
        .filter(InventoryTransaction.created_at >= cutoff)
        .all()
    )
    return sum(1 for (created_at,) in rows if to_local(created_at).date() >= first)
