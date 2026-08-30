# -*- coding: utf-8 -*-
"""Copy the local product images up to R2.

    python scripts/migrate_uploads_to_r2.py             # dry run - prints the plan
    python scripts/migrate_uploads_to_r2.py --commit    # uploads

The stored value in product.image is just a filename, and it stays the same —
only where that filename is served from changes. So this copies files up and
changes nothing in the database, which means:

  * the local files are NOT deleted (delete them yourself once you are happy)
  * flipping STORAGE_BACKEND back to local works instantly if anything is off

Every upload is read back with a HEAD request before it counts as done, so a
half-finished run can be re-run safely — anything already up is skipped.
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import Product
from utils.storage import R2Storage

UPLOAD_FOLDER = "uploads"


def human(size):
    if size >= 1048576:
        return f"{size / 1048576:.2f} MB"
    return f"{size / 1024:.1f} KB"


def build_client():
    account = os.getenv("R2_ACCOUNT_ID", "").strip()
    endpoint = os.getenv("R2_ENDPOINT", "").strip() or (
        f"https://{account}.r2.cloudflarestorage.com" if account else ""
    )

    required = {
        "R2_BUCKET": os.getenv("R2_BUCKET", "").strip(),
        "R2_PUBLIC_BASE": os.getenv("R2_PUBLIC_BASE", "").strip(),
        "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
    }
    missing = [k for k, v in required.items() if not v]
    if not endpoint:
        missing.append("R2_ACCOUNT_ID (أو R2_ENDPOINT)")

    if missing:
        print("✗ ناقص بملف .env:")
        for k in missing:
            print("    " + k)
        print()
        print("  حطّيهم بـ .env وأعيدي التشغيل. المفاتيح ما بتنحفظ بأي مكان تاني.")
        sys.exit(1)

    return R2Storage(
        bucket=required["R2_BUCKET"],
        public_base=required["R2_PUBLIC_BASE"],
        endpoint=endpoint,
        access_key=required["R2_ACCESS_KEY_ID"],
        secret_key=required["R2_SECRET_ACCESS_KEY"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="actually upload (default is a dry run)")
    args = parser.parse_args()

    storage = build_client()

    with app.app_context():
        products = Product.query.filter(
            Product.image.isnot(None), Product.image != ""
        ).order_by(Product.id).all()

    todo, already, missing = [], [], []

    for product in products:
        path = os.path.join(UPLOAD_FOLDER, product.image)
        if not os.path.exists(path):
            missing.append(product)
            continue
        if storage.exists(product.image):
            already.append(product)
            continue
        todo.append((product, path, os.path.getsize(path)))

    total = sum(size for _, _, size in todo)

    print("=" * 66)
    print(f"الوجهة: {storage.public_base}")
    print(f"الـbucket: {storage.bucket}")
    print("=" * 66)
    print(f"  للرفع:        {len(todo)} صورة ({human(total)})")
    print(f"  مرفوعة مسبقاً: {len(already)}")
    if missing:
        print(f"  ⚠ ملفها مفقود محلياً: {len(missing)}")
        for p in missing[:5]:
            print(f"      #{p.id} {p.name[:38]} ({p.image})")

    if not todo:
        print()
        print("ما في شي للرفع ✓")
        return

    if not args.commit:
        print()
        for product, path, size in todo[:8]:
            print(f"      {human(size):>9}  {product.name[:40]}")
        if len(todo) > 8:
            print(f"      … و{len(todo) - 8} غيرها")
        print()
        print("هذه تجربة فقط — لم يُرفع أي شيء.")
        print("للتنفيذ الفعلي:  python scripts/migrate_uploads_to_r2.py --commit")
        return

    print()
    done, failed = 0, []

    for product, path, size in todo:
        try:
            with open(path, "rb") as handle:
                storage.save(handle.read(), product.image)

            # only count it once R2 confirms it is really there
            if not storage.exists(product.image):
                raise RuntimeError("رُفعت بس ما ظهرت بالـbucket")

            done += 1
            print(f"  ✓ {done}/{len(todo)}  {product.name[:44]}")

        except Exception as exc:
            failed.append((product, str(exc)))
            print(f"  ✗ {product.name[:44]} — {exc}")

    print()
    print("=" * 66)
    print(f"✓ اترفع: {done} / {len(todo)}")

    if failed:
        print(f"✗ فشل: {len(failed)}")
        for product, why in failed:
            print(f"    #{product.id} {product.name[:36]} — {why}")
        print()
        print("الملفات المحلية زي ما هي — أعيدي تشغيل السكربت لإكمال الناقص.")
        sys.exit(1)

    print()
    print("الخطوة الجاية:")
    print("  1. حطّي STORAGE_BACKEND=r2 بملف .env")
    print("  2. أعيدي تشغيل التطبيق وافحصي إنه الصور بتظهر")
    print("  3. بعد ما تتأكدي، احذفي مجلد uploads/ المحلي")
    print()
    print("  الملفات المحلية ما انحذفت — لو صار إشي، رجّعي STORAGE_BACKEND=local")


if __name__ == "__main__":
    main()
