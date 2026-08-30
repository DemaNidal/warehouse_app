# -*- coding: utf-8 -*-
"""Re-encode the images that were uploaded before compression existed.

The catalogue holds 92 files averaging 2.7 MB, one of them 78 MB at 8192px —
sizes that make the product list a 32 MB page load and every nightly backup a
full copy of the folder. This resizes each one to the same web size new
uploads get and points the product row at the new file.

    python scripts/compress_uploads.py             # dry run - prints the plan
    python scripts/compress_uploads.py --commit    # writes it

Originals are MOVED to uploads/_originals/, never deleted, so a bad result can
be put back. Delete that folder yourself once the images look right.
"""

import os
import sys
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Product
from utils.images import optimize, ImageError, OUTPUT_EXTENSION

UPLOAD_FOLDER = "uploads"
ORIGINALS_FOLDER = os.path.join(UPLOAD_FOLDER, "_originals")


def human(size):
    if size >= 1048576:
        return f"{size / 1048576:.2f} MB"
    return f"{size / 1024:.1f} KB"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="actually write the changes (default is a dry run)")
    args = parser.parse_args()

    with app.app_context():

        products = Product.query.filter(
            Product.image.isnot(None),
            Product.image != ""
        ).order_by(Product.id).all()

        referenced = {p.image for p in products}
        on_disk = {
            f for f in os.listdir(UPLOAD_FOLDER)
            if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))
        }
        orphans = on_disk - referenced

        print("=" * 70)
        print(f"المنتجات اللي إلها صورة: {len(products)}")
        print("=" * 70)

        total_before = 0
        total_after = 0
        planned = []
        failed = []
        missing = []

        for product in products:
            source = os.path.join(UPLOAD_FOLDER, product.image)

            if not os.path.exists(source):
                missing.append(product)
                continue

            before = os.path.getsize(source)

            try:
                data = optimize(source)
            except ImageError as exc:
                failed.append((product, str(exc)))
                continue
            except Exception as exc:
                failed.append((product, f"{type(exc).__name__}: {exc}"))
                continue

            after = len(data)

            # already small and already webp? leave it alone
            if product.image.lower().endswith(f".{OUTPUT_EXTENSION}") and after >= before:
                continue

            stem = product.image.rsplit(".", 1)[0]
            new_name = f"{stem}.{OUTPUT_EXTENSION}"

            total_before += before
            total_after += after
            planned.append((product, source, new_name, data, before, after))

        for product, source, new_name, data, before, after in planned[:12]:
            saved = 100 - (after / before * 100) if before else 0
            print(f"  {human(before):>10} -> {human(after):>9}  ({saved:4.1f}%-)  {product.name[:34]}")
        if len(planned) > 12:
            print(f"  … و{len(planned) - 12} صورة غيرها")

        print()
        print("=" * 70)
        if total_before:
            print(f"  الحجم:  {human(total_before)}  ->  {human(total_after)}"
                  f"   (توفير {100 - total_after / total_before * 100:.1f}%)")
        print(f"  الصور:  {len(planned)} صورة رح تتحوّل")

        if missing:
            print(f"\n  ⚠  {len(missing)} منتج ملفه مفقود من القرص:")
            for p in missing[:5]:
                print(f"      #{p.id} {p.name[:40]}  ({p.image})")

        if failed:
            print(f"\n  ⚠  {len(failed)} صورة تعذّرت قراءتها (رح تُترك زي ما هي):")
            for p, why in failed[:5]:
                print(f"      #{p.id} {p.name[:34]}  — {why}")

        if orphans:
            orphan_size = sum(
                os.path.getsize(os.path.join(UPLOAD_FOLDER, f)) for f in orphans
            )
            print(f"\n  ℹ  {len(orphans)} ملف مش مرتبط بأي منتج ({human(orphan_size)}) — "
                  f"ما رح نلمسها")

        if not args.commit:
            print()
            print("هذه تجربة فقط — لم يتم حفظ أي شيء.")
            print("للتنفيذ الفعلي:  python scripts/compress_uploads.py --commit")
            return

        os.makedirs(ORIGINALS_FOLDER, exist_ok=True)
        done = 0

        for product, source, new_name, data, before, after in planned:
            target = os.path.join(UPLOAD_FOLDER, new_name)

            # write the new file first, then move the original aside, then
            # point the row at it — so a crash never leaves a row pointing at
            # a file that is gone
            with open(target, "wb") as handle:
                handle.write(data)

            if os.path.abspath(source) != os.path.abspath(target):
                shutil.move(source, os.path.join(ORIGINALS_FOLDER, os.path.basename(source)))

            product.image = new_name
            done += 1

        db.session.commit()

        print()
        print(f"✓ تم — {done} صورة")
        print(f"  الأصول محفوظة بـ {ORIGINALS_FOLDER}/ — احذفيها بعد ما تتأكدي")


if __name__ == "__main__":
    main()
