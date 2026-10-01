# -*- coding: utf-8 -*-
"""Move existing archives from the image bucket into the dedicated one.

The archives started life under a `backups/` prefix in the image bucket, mixed
in with 168 product photos. Once `R2_BACKUP_BUCKET` exists they belong there
instead, and the old copies should go — a database archive sitting in a bucket
whose keys the web application carries is the exposure the split was meant to
remove.

Copies first, verifies every object arrived with the same size, and only then
offers to delete the originals.

    python scripts/migrate_backups_bucket.py              # dry run
    python scripts/migrate_backups_bucket.py --commit     # copy
    python scripts/migrate_backups_bucket.py --commit --delete-source
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# run standalone as well as imported: nothing else loads the environment when
# this is invoked directly from a shell or cron
from dotenv import load_dotenv
load_dotenv()

import boto3
from botocore.config import Config

SOURCE_PREFIX = "backups/"


def _endpoint():
    account = os.getenv("R2_ACCOUNT_ID", "").strip()
    return os.getenv("R2_ENDPOINT", "").strip() or (
        f"https://{account}.r2.cloudflarestorage.com" if account else ""
    )


def _client(key, secret):
    return boto3.session.Session().client(
        "s3",
        endpoint_url=_endpoint(),
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--delete-source", action="store_true",
                        help="remove the originals after verifying the copies")
    args = parser.parse_args()

    src_bucket = os.getenv("R2_BUCKET", "").strip()
    dst_bucket = os.getenv("R2_BACKUP_BUCKET", "").strip()

    if not dst_bucket:
        raise SystemExit(
            "R2_BACKUP_BUCKET مش مضبوط بـ.env — أنشئي الحاوية وحطي اسمها أولاً"
        )

    src = _client(os.getenv("R2_ACCESS_KEY_ID", "").strip(),
                  os.getenv("R2_SECRET_ACCESS_KEY", "").strip())

    dst = _client(
        os.getenv("R2_BACKUP_ACCESS_KEY_ID", "").strip()
        or os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        os.getenv("R2_BACKUP_SECRET_ACCESS_KEY", "").strip()
        or os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
    )

    print(f"من : {src_bucket}/{SOURCE_PREFIX}")
    print(f"إلى: {dst_bucket}/")
    print()

    listing = src.list_objects_v2(Bucket=src_bucket, Prefix=SOURCE_PREFIX)
    objects = listing.get("Contents", [])

    if not objects:
        print("ما في نسخ بالحاوية القديمة — يمكن سبق ونُقلت.")
        return

    # The two buckets may not share credentials, so this downloads and
    # re-uploads rather than asking R2 to copy server-side.
    moved, failed = [], []
    for obj in sorted(objects, key=lambda o: o["LastModified"]):
        name = obj["Key"][len(SOURCE_PREFIX):]
        size_kb = obj["Size"] / 1024

        if not args.commit:
            print(f"  سينقل: {name:<34} {size_kb:>7.1f} كيلو")
            continue

        body = src.get_object(Bucket=src_bucket, Key=obj["Key"])["Body"].read()
        dst.put_object(Bucket=dst_bucket, Key=name, Body=body)

        check = dst.head_object(Bucket=dst_bucket, Key=name)
        if check["ContentLength"] == obj["Size"]:
            moved.append(obj["Key"])
            print(f"  ✓ {name:<34} {size_kb:>7.1f} كيلو")
        else:
            failed.append(name)
            print(f"  ✗ {name} — الحجم مختلف بعد النسخ")

    print()
    if not args.commit:
        print(f"تجربة فقط — {len(objects)} نسخة.")
        print("للتنفيذ:  python scripts/migrate_backups_bucket.py --commit")
        return

    print(f"نُقلت: {len(moved)}   فشلت: {len(failed)}")

    if failed:
        print("ما بحذف الأصل طالما في نسخة فشلت.")
        return

    if not args.delete_source:
        print()
        print("الأصل لسا موجود بالحاوية القديمة. لحذفه بعد ما تتأكدي:")
        print("  python scripts/migrate_backups_bucket.py --commit --delete-source")
        return

    src.delete_objects(
        Bucket=src_bucket,
        Delete={"Objects": [{"Key": k} for k in moved]},
    )
    print(f"✓ حُذفت {len(moved)} نسخة من الحاوية القديمة")


if __name__ == "__main__":
    main()
