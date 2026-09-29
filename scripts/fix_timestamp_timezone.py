# -*- coding: utf-8 -*-
"""Correct timestamps written before the system settled on UTC.

Columns that defaulted to `datetime.now` stored the machine's local time;
columns that defaulted to `db.func.now()` stored PostgreSQL's, which runs on
`TimeZone = GMT` and so was already UTC. The two disagreed by the local offset,
which is how a product ended up created at 11:12 and updated at 14:12 in the
same instant.

Everything is UTC now (see utils/clock). This shifts the rows that were written
the other way, once.

Conversion goes through the zone rather than subtracting a fixed number of
hours: Palestine moves on and off summer time, so the same wall-clock hour is
+03 in August and +02 in December, and rows from both exist.

    python scripts/fix_timestamp_timezone.py             # dry run
    python scripts/fix_timestamp_timezone.py --commit    # writes it
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db
from sqlalchemy import text
from utils.clock import local_to_utc, to_local

# (table, column) pairs whose default was `datetime.now` — local time.
# product.created_at and inventory_transaction.created_at are deliberately
# absent: they came from db.func.now() and are already UTC.
LOCAL_COLUMNS = [
    ("product", "updated_at"),
    ("activity_log", "created_at"),
    ("notification", "created_at"),
    ("stock_request", "created_at"),
    ("stock_request", "approved_at"),
    ("stock_request", "rejected_at"),
    ("customer", "created_at"),
    ("category", "created_at"),
    ('"user"', "created_at"),
]

MARKER_TABLE = "timestamp_timezone_fixed"


def already_applied(conn):
    """A marker row, so running this twice cannot shift the data twice."""
    exists = conn.execute(text(
        "select count(*) from information_schema.tables "
        "where table_schema='public' and table_name=:t"
    ), {"t": MARKER_TABLE}).scalar()
    return bool(exists)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="actually write (default is a dry run)")
    args = parser.parse_args()

    with app.app_context():
        conn = db.session

        if already_applied(conn):
            print("سبق وانطبق التصحيح — ما في إشي للعمل.")
            print(f"(علامة: جدول {MARKER_TABLE})")
            return

        print("=" * 68)
        print("الأعمدة اللي كانت تُكتب بتوقيت الجهاز، والتصحيح المقترح")
        print("=" * 68)

        total = 0
        for table, column in LOCAL_COLUMNS:
            rows = conn.execute(text(
                f"select id, {column} from {table} where {column} is not null "
                f"order by id"
            )).fetchall()

            if not rows:
                print(f"\n  {table}.{column}: لا صفوف")
                continue

            total += len(rows)
            sample = rows[0]
            shifted = local_to_utc(sample[1])
            delta = (sample[1] - shifted).total_seconds() / 3600

            print(f"\n  {table}.{column}  —  {len(rows)} صف")
            print(f"     مثال: {sample[1]:%Y-%m-%d %H:%M}  →  {shifted:%Y-%m-%d %H:%M} "
                  f"UTC  (−{delta:.0f} ساعة)")
            print(f"     وبيتعرض للمستخدم: {to_local(shifted):%Y-%m-%d %H:%M}  "
                  f"← نفس اللي كان ظاهر")

            if args.commit:
                for row_id, value in rows:
                    conn.execute(
                        text(f"update {table} set {column} = :v where id = :i"),
                        {"v": local_to_utc(value), "i": row_id},
                    )

        print()
        print("=" * 68)
        print(f"إجمالي الصفوف: {total}")

        if not args.commit:
            print()
            print("تجربة فقط — ما تغيّر إشي.")
            print("للتنفيذ:  python scripts/fix_timestamp_timezone.py --commit")
            return

        conn.execute(text(
            f"create table {MARKER_TABLE} "
            "(applied_at timestamp not null default (now() at time zone 'utc'))"
        ))
        conn.execute(text(f"insert into {MARKER_TABLE} default values"))
        conn.commit()

        print()
        print(f"✓ تم — {total} صف، والعلامة انحطت فما بينعاد التصحيح مرتين")


if __name__ == "__main__":
    main()
