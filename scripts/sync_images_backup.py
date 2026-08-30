# -*- coding: utf-8 -*-
"""Pull a local copy of every image out of R2.

R2 keeps the bucket durable, but nothing protects it from a mistake: a wrong
script, a deleted bucket, a revoked token. Since the nightly database backup
stopped carrying images, this is the only second copy there is.

    python scripts/sync_images_backup.py               # sync
    python scripts/sync_images_backup.py --dry-run     # show what would change
    python scripts/sync_images_backup.py --prune       # also drop local extras

By design this NEVER deletes a local file just because it vanished from R2 —
a backup that mirrors deletions is not a backup, it just copies the accident.
Use --prune deliberately when you know the removal was intentional.
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DEST = os.path.join("backups", "images")


def human(size):
    if size >= 1048576:
        return f"{size / 1048576:.2f} MB"
    return f"{size / 1024:.1f} KB"


def build_client():
    from utils.storage import R2Storage

    account = os.getenv("R2_ACCOUNT_ID", "").strip()
    endpoint = os.getenv("R2_ENDPOINT", "").strip() or (
        f"https://{account}.r2.cloudflarestorage.com" if account else ""
    )

    required = {
        "R2_BUCKET": os.getenv("R2_BUCKET", "").strip(),
        "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
    }
    missing = [k for k, v in required.items() if not v]
    if not endpoint:
        missing.append("R2_ACCOUNT_ID (أو R2_ENDPOINT)")

    if missing:
        print("✗ ناقص بملف .env: " + "، ".join(missing))
        sys.exit(1)

    return R2Storage(
        bucket=required["R2_BUCKET"],
        public_base=os.getenv("R2_PUBLIC_BASE", "").strip() or "https://example.invalid",
        endpoint=endpoint,
        access_key=required["R2_ACCESS_KEY_ID"],
        secret_key=required["R2_SECRET_ACCESS_KEY"],
    )


def list_remote(storage):
    """Every object in the bucket, as {key: size}."""
    objects = {}
    paginator = storage.client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=storage.bucket):
        for item in page.get("Contents", []):
            objects[item["Key"]] = item["Size"]
    return objects


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", default=DEFAULT_DEST,
                        help=f"مجلد النسخة المحلية (افتراضي: {DEFAULT_DEST})")
    parser.add_argument("--dry-run", action="store_true",
                        help="اعرض شو رح يتغيّر بدون ما تنزّل")
    parser.add_argument("--prune", action="store_true",
                        help="احذف الملفات المحلية اللي ما عادت موجودة بـR2")
    args = parser.parse_args()

    storage = build_client()
    dest = args.dest

    print("=" * 62)
    print(f"من:  {storage.bucket}")
    print(f"إلى: {os.path.abspath(dest)}")
    print("=" * 62)

    remote = list_remote(storage)
    os.makedirs(dest, exist_ok=True)

    MANIFEST = "_manifest.txt"

    local = {
        name: os.path.getsize(os.path.join(dest, name))
        for name in os.listdir(dest)
        if os.path.isfile(os.path.join(dest, name)) and name != MANIFEST
    }

    # size is enough to spot a changed object here: filenames carry a UUID, so
    # a replaced image gets a new name rather than overwriting an old one
    to_download = [k for k, size in remote.items()
                   if k not in local or local[k] != size]
    up_to_date = len(remote) - len(to_download)
    extra = sorted(set(local) - set(remote))

    print(f"  بـR2:            {len(remote)} ملف ({human(sum(remote.values()))})")
    print(f"  محفوظة محلياً:   {up_to_date}")
    print(f"  للتنزيل:         {len(to_download)}"
          f" ({human(sum(remote[k] for k in to_download))})")

    if extra:
        print(f"  محلية بس مش بـR2: {len(extra)}"
              f" — {'رح تنحذف' if args.prune else 'رح تُترك (شبكة أمانك)'}")
        for name in extra[:5]:
            print(f"      {name}")

    if args.dry_run:
        print()
        print("تجربة فقط — ما تغيّر إشي.")
        return

    if not to_download and not (args.prune and extra):
        print()
        print("كل شي محدّث ✓")
        _write_manifest(dest, remote)
        return

    print()
    done, failed = 0, []
    for key in to_download:
        try:
            path = os.path.join(dest, os.path.basename(key))
            storage.client.download_file(storage.bucket, key, path)
            done += 1
            if done % 20 == 0 or done == len(to_download):
                print(f"  … {done}/{len(to_download)}")
        except Exception as exc:
            failed.append((key, str(exc)[:80]))

    pruned = 0
    if args.prune:
        for name in extra:
            os.remove(os.path.join(dest, name))
            pruned += 1

    print()
    print("=" * 62)
    print(f"✓ اتنزّل: {done}")
    if pruned:
        print(f"  انحذف محلياً: {pruned}")
    if failed:
        print(f"✗ فشل: {len(failed)}")
        for key, why in failed[:5]:
            print(f"    {key} — {why}")
        sys.exit(1)

    _write_manifest(dest, remote)

    files = [f for f in os.listdir(dest)
             if os.path.isfile(os.path.join(dest, f)) and f != "_manifest.txt"]
    total = sum(os.path.getsize(os.path.join(dest, f)) for f in files)
    print(f"  النسخة المحلية الآن: {len(files)} صورة ({human(total)})")


def _write_manifest(dest, remote):
    """A dated record of what the bucket held, so a restore knows what to expect."""
    path = os.path.join(dest, "_manifest.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"# مزامنة: {datetime.now():%Y-%m-%d %H:%M}\n")
        handle.write(f"# عدد الملفات: {len(remote)}\n\n")
        for key in sorted(remote):
            handle.write(f"{remote[key]}\t{key}\n")


if __name__ == "__main__":
    main()
