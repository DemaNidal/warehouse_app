# -*- coding: utf-8 -*-
"""Canonicalise size names that were entered in inconsistent formats.

Neck sizes went in as both "28\\410" and "24/410". Same measurement, two
spellings, so filtering or fit-matching on neck size silently misses rows.

    python scripts/normalize_sizes.py             # dry run - prints the plan
    python scripts/normalize_sizes.py --commit    # writes it

If normalising a name collides with a size that already exists, the products
are repointed at the survivor and the now-empty duplicate is deleted, so no
product is ever left orphaned.
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Size, Product
from utils.validation.size import normalize_size_name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit",
        action="store_true",
        help="actually write the changes (default is a dry run)"
    )
    args = parser.parse_args()

    with app.app_context():

        sizes = Size.query.order_by(Size.id).all()
        by_canonical = {}

        # Pass 1: whoever already holds the canonical spelling wins the merge
        for size in sizes:
            if normalize_size_name(size.name) == size.name:
                by_canonical.setdefault(size.name, size)

        renames = []
        merges = []

        # Pass 2: everything else is either renamed or folded into the winner
        for size in sizes:
            canonical = normalize_size_name(size.name)

            if canonical == size.name:
                continue

            winner = by_canonical.get(canonical)

            if winner is None:
                by_canonical[canonical] = size
                renames.append((size, canonical))
            else:
                merges.append((size, winner))

        if not renames and not merges:
            print("كل المقاسات بصيغة موحّدة ✓")
            return

        print("=" * 62)
        print("الخطة")
        print("=" * 62)

        for size, canonical in renames:
            count = Product.query.filter_by(size_id=size.id).count()
            print(f"\n  إعادة تسمية:  «{size.name}»  ->  «{canonical}»")
            print(f"                {count} منتج مرتبط، بيضلوا مربوطين بنفس الصف")

        for size, winner in merges:
            count = Product.query.filter_by(size_id=size.id).count()
            print(f"\n  دمج:  «{size.name}»  ->  «{winner.name}» (id={winner.id})")
            print(f"        {count} منتج بينتقلوا، وبعدها ينحذف الصف الفاضي")

        print()
        print("=" * 62)

        if not args.commit:
            db.session.rollback()
            print("هذه تجربة فقط — لم يتم حفظ أي شيء.")
            print("للتنفيذ الفعلي:  python scripts/normalize_sizes.py --commit")
            return

        for size, canonical in renames:
            size.name = canonical

        for size, winner in merges:
            Product.query.filter_by(size_id=size.id).update(
                {"size_id": winner.id},
                synchronize_session=False
            )
            db.session.delete(size)

        db.session.commit()
        print("✓ تم الحفظ")


if __name__ == "__main__":
    main()
