# -*- coding: utf-8 -*-
"""Seed the default categories and assign one to every existing product.

Products entered before categories existed all have category_id = NULL. This
walks them through the keyword rules in utils/categorization.py.

    python scripts/backfill_categories.py             # dry run - prints the plan
    python scripts/backfill_categories.py --commit    # writes it

The dry run is the default on purpose: 91 rows is small enough to read, and a
wrong category is easier to prevent than to unpick afterwards. Re-running is
safe - products that already have a category are never touched.
"""

import os
import sys
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Category, Product
from utils.categorization import DEFAULT_CATEGORIES, suggest_category, normalize


def seed_categories(commit):
    """Create any missing default category. Existing ones are left alone.

    Returns (created_names, effective_categories). On a dry run the missing
    ones are built in memory but never added to the session, so the plan below
    can still be printed on a first run - which is exactly when you want to
    read it before anything is written.
    """

    existing = {normalize(c.name): c for c in Category.query.all()}
    created = []
    effective = list(existing.values())

    for name, slug, icon, order in DEFAULT_CATEGORIES:
        if normalize(name) in existing:
            continue

        category = Category(name=name, slug=slug, icon=icon, sort_order=order)
        created.append(name)
        effective.append(category)

        if commit:
            db.session.add(category)

    if commit and created:
        db.session.flush()

    return created, effective


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--commit",
        action="store_true",
        help="actually write the changes (default is a dry run)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="also re-assign products that already have a category"
    )
    args = parser.parse_args()

    with app.app_context():

        created, categories = seed_categories(args.commit)

        if created:
            print("تصنيفات جديدة:", "، ".join(created))
        else:
            print("كل التصنيفات الافتراضية موجودة مسبقاً")
        print()

        query = Product.query.order_by(Product.name)
        if not args.all:
            query = query.filter(Product.category_id.is_(None))

        products = query.all()

        if not products:
            print("لا توجد منتجات بحاجة لتصنيف ✓")
            return

        planned = defaultdict(list)
        unmatched = []

        for product in products:
            match = suggest_category(product.name, categories)

            if match is None:
                unmatched.append(product)
                continue

            planned[match.name].append(product)

            if args.commit:
                product.category_id = match.id

        print("=" * 66)
        print(f"الخطة — {len(products)} منتج")
        print("=" * 66)

        for name in sorted(planned, key=lambda k: -len(planned[k])):
            items = planned[name]
            print(f"\n  ▸ {name}  ({len(items)} منتج)")
            for product in items:
                size = product.size_data.name if product.size_data else "-"
                print(f"      #{product.id:<4} {product.name}  ({size})")

        if unmatched:
            print(f"\n  ▸ بدون تطابق  ({len(unmatched)} منتج) — بدها تصنيف يدوي")
            for product in unmatched:
                print(f"      #{product.id:<4} {product.name}")

        matched = len(products) - len(unmatched)
        print()
        print("=" * 66)
        print(f"سيُصنَّف: {matched} / {len(products)}")

        if args.commit:
            db.session.commit()
            print("✓ تم الحفظ")
        else:
            db.session.rollback()
            print("هذه تجربة فقط — لم يتم حفظ أي شيء.")
            print("للتنفيذ الفعلي:  python scripts/backfill_categories.py --commit")


if __name__ == "__main__":
    main()
