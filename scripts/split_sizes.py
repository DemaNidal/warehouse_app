# -*- coding: utf-8 -*-
"""Separate capacities from neck sizes in the Size table.

Both used to live in one column with no way to tell them apart, so a bottle
could record how much it holds OR what cap fits it — never both. This tags
each size with its kind, then moves every product whose size is really a neck
size over to Product.neck_size_id, freeing size_id to mean capacity only.

    python scripts/split_sizes.py             # dry run - prints the plan
    python scripts/split_sizes.py --commit    # writes it

Nothing is invented: a cap that only ever had a neck size ends up with no
capacity, and a bottle that only had a capacity ends up with no neck size.
The second gap is the point — it becomes visible and fillable instead of
being silently impossible to record.
"""

import os
import re
import sys
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Size, Product, SIZE_KIND_CAPACITY, SIZE_KIND_NECK

# "28/410" — an explicit neck finish
NECK_EXPLICIT = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
# "500 مل" / "1 لتر" / "48.7 غم" — a quantity the container holds
CAPACITY_UNIT = re.compile(r"(مل|لتر|غم|كغم)")
# "33", "38", "89" — a bare number, only ever used on caps here
BARE_NUMBER = re.compile(r"^\s*[\d.]+\s*$")


def classify(name):
    """Return (kind, confident). Bare numbers are flagged for review."""

    if NECK_EXPLICIT.match(name):
        return SIZE_KIND_NECK, True

    if CAPACITY_UNIT.search(name):
        return SIZE_KIND_CAPACITY, True

    if BARE_NUMBER.match(name):
        # No unit to go on. Every bare number in this catalogue sits on a cap
        # or a pump, so it is a neck — but say so out loud rather than assume.
        return SIZE_KIND_NECK, False

    return SIZE_KIND_CAPACITY, False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="actually write the changes (default is a dry run)")
    args = parser.parse_args()

    with app.app_context():

        sizes = Size.query.order_by(Size.id).all()

        plan = defaultdict(list)
        unsure = []

        for size in sizes:
            kind, confident = classify(size.name)
            plan[kind].append(size)
            if not confident:
                unsure.append((size, kind))

        print("=" * 66)
        print("١) تصنيف القياسات")
        print("=" * 66)

        for kind, label in [(SIZE_KIND_CAPACITY, "السعة"), (SIZE_KIND_NECK, "مقاس الرقبة")]:
            items = plan[kind]
            print(f"\n  ▸ {label}  ({len(items)} قيمة)")
            print("      " + "، ".join(s.name for s in items))

        if unsure:
            print("\n  ⚠  بدون وحدة قياس — خمّنتها، راجعيها:")
            for size, kind in unsure:
                users = Product.query.filter_by(size_id=size.id).all()
                names = "، ".join(p.name for p in users[:3])
                more = f" (+{len(users) - 3})" if len(users) > 3 else ""
                print(f"      «{size.name}» -> {kind}   [{names}{more}]")

        # ---- which products move to neck_size_id ----
        neck_ids = {s.id for s in plan[SIZE_KIND_NECK]}
        movers = Product.query.filter(Product.size_id.in_(neck_ids)).all() if neck_ids else []
        keepers = Product.query.filter(
            Product.size_id.isnot(None),
            ~Product.size_id.in_(neck_ids) if neck_ids else True
        ).all()

        print()
        print("=" * 66)
        print("٢) نقل المنتجات")
        print("=" * 66)
        print(f"\n  ينتقلون إلى neck_size_id: {len(movers)} منتج")
        print(f"  (قياسهم مقاس رقبة، فما إلهم سعة مسجّلة — وهاد صحيح لأغطية وبمبات)")
        for p in movers[:8]:
            print(f"      #{p.id:<4} {p.name}  ({p.size_data.name if p.size_data else '-'})")
        if len(movers) > 8:
            print(f"      … و{len(movers) - 8} غيرهم")

        print(f"\n  يبقون على size_id كسعة: {len(keepers)} منتج")
        print(f"  (مقاس رقبتهم غير مسجّل — هاي الفجوة اللي بدنا نعبّيها لاحقاً)")

        print()
        print("=" * 66)

        if not args.commit:
            db.session.rollback()
            print("هذه تجربة فقط — لم يتم حفظ أي شيء.")
            print("للتنفيذ الفعلي:  python scripts/split_sizes.py --commit")
            return

        for kind in (SIZE_KIND_CAPACITY, SIZE_KIND_NECK):
            for size in plan[kind]:
                size.kind = kind

        for product in movers:
            product.neck_size_id = product.size_id
            product.size_id = None

        db.session.commit()
        print(f"✓ تم الحفظ — {len(movers)} منتج انتقلوا، {len(sizes)} قياس اتصنّفوا")


if __name__ == "__main__":
    main()
