# -*- coding: utf-8 -*-
"""Rebuild the searchable text for every product.

Run it once after the migration, and again any time a colour, size or category
gets renamed — those names are copied into each product's search_text, so a
rename elsewhere leaves the copies stale until this runs.

    python scripts/rebuild_search_text.py             # dry run
    python scripts/rebuild_search_text.py --commit    # writes it
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Product
from sqlalchemy.orm import joinedload
from utils.search_text import build_search_text, refresh_search_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="actually write (default is a dry run)")
    args = parser.parse_args()

    with app.app_context():
        products = (
            Product.query
            .options(
                joinedload(Product.color),
                joinedload(Product.secondary_color),
                joinedload(Product.category),
                joinedload(Product.size_data),
                joinedload(Product.neck_size),
            )
            .order_by(Product.id)
            .all()
        )

        changed = []
        for product in products:
            fresh = build_search_text(product)

            if fresh != (product.search_text or ""):
                changed.append((product, fresh))
                if args.commit:
                    refresh_search_text(product)

        print("=" * 66)
        print(f"المنتجات: {len(products)}")
        print(f"بحاجة تحديث: {len(changed)}")
        print("=" * 66)

        for product, fresh in changed[:8]:
            print(f"\n  #{product.id}  {product.name[:44]}")
            print(f"      {fresh[:96]}")
        if len(changed) > 8:
            print(f"\n  … و{len(changed) - 8} غيرها")

        if not changed:
            print("\nكل شي محدّث ✓")
            return

        if not args.commit:
            print()
            print("تجربة فقط — ما تغيّر إشي.")
            print("للتنفيذ:  python scripts/rebuild_search_text.py --commit")
            return

        db.session.commit()
        print()
        print(f"✓ تم — {len(changed)} منتج")


if __name__ == "__main__":
    main()
