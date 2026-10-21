# -*- coding: utf-8 -*-
"""Give every product a reorder point of its own.

All 243 products carry minimum_stock = 1000. The catalogue runs from 402
units to 1,755,000, so that one number means "always alarming" for the small
items and "never alarming" for the large ones: a product holding 200,000
would have to lose 99.5% of its stock before the dashboard said a word.

What it is NOT computed from
----------------------------
Consumption. Only 21 of 243 products have any outflow recorded, and nearly
all of those have exactly one — not because the recording is poor but
because this is a wholesale business three months into using the system:
25 shipments in twelve weeks, matching 25 approved stock requests exactly.
There is no rate to measure for the other 92%.

What it IS computed from
------------------------
Each product's own typical intake batch. A product bought in lots of 8,832
is a different size of thing from one bought in lots of 150, and the lot is
the working quantity for that item. Half a lot is the threshold, because
that is where the data says a warning can still be early:

    94% of products sit at 90%+ of their batch — full, untouched
     7  sit at exactly zero
     8  sit part-way down, between 33% and 88%
     0  sit between 0% and 25%

A threshold at a quarter of a batch therefore fires only once the shelf is
already empty, which is a report, not a warning. Half a batch catches five
products while they still have stock.

This is a defensible starting point, not a derived optimum — twelve weeks
and twenty-five shipments cannot support one. Every value is editable per
product from the edit screen, and this script will never overwrite a value
a person has changed.

    python scripts/suggest_minimum_stock.py              # show, change nothing
    python scripts/suggest_minimum_stock.py --commit     # apply
    python scripts/suggest_minimum_stock.py --revert     # put back what was there
"""

import argparse
import io
import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from app import app                                        # noqa: E402
from models import InventoryTransaction, Product, db       # noqa: E402

SHARE_OF_BATCH = 0.5
FALLBACK = 1000
LEDGER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "instance", "minimum_stock_ledger.json",
)


def rounded(value):
    """To a number a person would actually write down."""
    if value <= 0:
        return 0
    for ceiling, step in ((200, 10), (2_000, 50), (20_000, 100),
                          (200_000, 1_000)):
        if value < ceiling:
            return max(step, int(round(value / step)) * step)
    return int(round(value / 10_000)) * 10_000


def intake_batches():
    """The arrival quantities for each product."""
    batches = defaultdict(list)
    rows = (
        db.session.query(
            InventoryTransaction.product_id,
            InventoryTransaction.quantity,
        )
        .filter(InventoryTransaction.transaction_type == "IN")
        .all()
    )
    for product_id, quantity in rows:
        if quantity:
            batches[product_id].append(quantity)
    return batches


def suggestions():
    """What each product's reorder point should be, and why."""
    batches = intake_batches()
    out = []

    for product in Product.query.order_by(Product.id).all():
        mine = batches.get(product.id)
        if mine:
            batch = statistics.median(mine)
            suggested = rounded(batch * SHARE_OF_BATCH)
            basis = f"{len(mine)} إدخال · الوسيط {int(batch):,}"
        else:
            batch = None
            suggested = FALLBACK
            basis = "ما في إدخالات — تُرك على الافتراضي"

        out.append({
            "id": product.id,
            "name": product.name,
            "quantity": product.total_quantity,
            "current": product.minimum_stock,
            "suggested": suggested,
            "batch": int(batch) if batch else None,
            "basis": basis,
        })
    return out


def load_ledger():
    """What this script set last time, so a person's edits are not undone."""
    try:
        with io.open(LEDGER, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {int(k): v for k, v in raw.items()}
    except (OSError, ValueError):
        return {}


def save_ledger(entries):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with io.open(LEDGER, "w", encoding="utf-8") as fh:
        json.dump({str(k): v for k, v in entries.items()}, fh,
                  ensure_ascii=False, indent=2)


def show(rows, ledger):
    changing = [r for r in rows if r["suggested"] != r["current"]]
    protected = [
        r for r in rows
        if r["id"] in ledger and r["current"] != ledger[r["id"]]["set_to"]
    ]

    print(f"{'المنتج':<34}{'الكمية':>11}{'الحد الآن':>11}"
          f"{'المقترح':>11}   على أي أساس")
    print("-" * 104)

    for row in sorted(rows, key=lambda r: -(r["suggested"] or 0))[:18]:
        mark = " *" if row in protected else "  "
        print(f"{row['name'][:32]:<34}{row['quantity']:>11,}"
              f"{row['current']:>11,}{row['suggested']:>11,}{mark} {row['basis']}")

    print("...")
    print()

    flagged_before = sum(1 for r in rows if r["quantity"] <= r["current"])
    flagged_after = sum(1 for r in rows if r["quantity"] <= r["suggested"])
    empty = sum(1 for r in rows if r["quantity"] == 0)

    print(f"  منتجات            : {len(rows)}")
    print(f"  رح يتغيّر حدّها    : {len(changing)}")
    if protected:
        print(f"  معدّلة بالإيد      : {len(protected)}  (ما رح تتلمس — معلّمة *)")
    print()
    print(f"  تنبيهات قبل       : {flagged_before:>3}   "
          f"({empty} منها فاضية فعلاً)")
    print(f"  تنبيهات بعد       : {flagged_after:>3}   "
          f"({empty} فاضية · {flagged_after - empty} تحذير مبكّر)")
    print()
    print("  «تحذير مبكّر» يعني منتج لسا عنده بضاعة بس نازل تحت نص دفعته —")
    print("  وهاد اللي الحد الثابت 1000 ما كان بيمسكه.")


def apply(rows, ledger, revert=False):
    touched = 0
    skipped = 0

    for row in rows:
        product = db.session.get(Product, row["id"])
        if product is None:
            continue

        previous = ledger.get(row["id"])
        if previous and product.minimum_stock != previous["set_to"]:
            # a person changed it since; their number wins
            skipped += 1
            continue

        if revert:
            if not previous:
                continue
            target = previous["was"]
        else:
            target = row["suggested"]

        if product.minimum_stock == target:
            continue

        if not revert:
            ledger[row["id"]] = {
                "was": previous["was"] if previous else product.minimum_stock,
                "set_to": target,
            }
        product.minimum_stock = target
        touched += 1

    db.session.commit()

    if revert:
        save_ledger({})
    else:
        save_ledger(ledger)

    print(f"\n  اتغيّر: {touched} منتج")
    if skipped:
        print(f"  انتُرك: {skipped} (معدّلين بالإيد بعد آخر تشغيل)")
    print(f"  السجل: {LEDGER}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true",
                        help="طبّق التغيير فعلياً")
    parser.add_argument("--revert", action="store_true",
                        help="رجّع القيم اللي كانت قبل آخر تطبيق")
    args = parser.parse_args()

    with app.app_context():
        rows = suggestions()
        ledger = load_ledger()

        if args.revert:
            if not ledger:
                print("ما في إشي أرجّعه — السجل فاضي.")
                return
            print(f"برجّع {len(ledger)} منتج لقيمهم السابقة…")
            apply(rows, ledger, revert=True)
            return

        show(rows, ledger)

        if args.commit:
            apply(rows, ledger)
        else:
            print()
            print("  هاي تجربة جافة — ما تغيّر ولا إشي.")
            print("  للتطبيق:  python scripts/suggest_minimum_stock.py --commit")
            print("  وللتراجع: python scripts/suggest_minimum_stock.py --revert")


if __name__ == "__main__":
    main()
