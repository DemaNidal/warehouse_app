# -*- coding: utf-8 -*-
"""Copy the newest backup archive into object storage.

A backup that lives on the same disk as the database is not a backup. It
survives a mistaken delete and nothing else — not a failed disk, not a
cancelled server, not a provider account problem. This puts the archive
somewhere with no shared failure mode.

Prefers its own bucket and its own credentials (`R2_BACKUP_*`). The application
runs on an internet-facing server and carries the keys for the image bucket; if
those leak, the backups should not be reachable with them. Falls back to the
image bucket under a `backups/` prefix when the separate ones are not
configured, so nothing breaks before they exist.

    python scripts/upload_backup_to_r2.py             # newest archive
    python scripts/upload_backup_to_r2.py --keep 30   # and prune older ones
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# run standalone as well as imported: nothing else loads the environment when
# this is invoked directly from a shell or cron
from dotenv import load_dotenv
load_dotenv()


def _settings():
    """Where the archives go, and with which keys.

    A dedicated bucket needs no prefix — the whole bucket is backups. The
    fallback shares the image bucket, so it keeps the prefix to stay out of
    the way of 168 product photos.
    """

    dedicated = os.getenv("R2_BACKUP_BUCKET", "").strip()

    if dedicated:
        return {
            "bucket": dedicated,
            "prefix": "",
            "key": (os.getenv("R2_BACKUP_ACCESS_KEY_ID", "").strip()
                    or os.getenv("R2_ACCESS_KEY_ID", "").strip()),
            "secret": (os.getenv("R2_BACKUP_SECRET_ACCESS_KEY", "").strip()
                       or os.getenv("R2_SECRET_ACCESS_KEY", "").strip()),
        }

    return {
        "bucket": os.getenv("R2_BUCKET", "").strip(),
        "prefix": "backups/",
        "key": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        "secret": os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
    }


def _client():
    """A client, the bucket to write to, and the prefix inside it."""

    import boto3
    from botocore.config import Config

    # the same two spellings utils.storage accepts, so one .env serves both
    account = os.getenv("R2_ACCOUNT_ID", "").strip()
    endpoint = os.getenv("R2_ENDPOINT", "").strip() or (
        f"https://{account}.r2.cloudflarestorage.com" if account else ""
    )

    cfg = _settings()

    missing = [name for name, value in [
        ("R2_BUCKET أو R2_BACKUP_BUCKET", cfg["bucket"]),
        ("مفتاح الوصول", cfg["key"]),
        ("المفتاح السري", cfg["secret"]),
    ] if not value]
    if not endpoint:
        missing.append("R2_ACCOUNT_ID (أو R2_ENDPOINT)")

    if missing:
        raise SystemExit("ناقص إعدادات R2: " + "، ".join(missing))

    session = boto3.session.Session()
    client = session.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=cfg["key"],
        aws_secret_access_key=cfg["secret"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )
    return client, cfg["bucket"], cfg["prefix"]


def newest_archive(folder="backups"):
    if not os.path.isdir(folder):
        return None

    archives = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.endswith(".zip")
    ]
    if not archives:
        return None

    return max(archives, key=os.path.getmtime)


def prune(client, bucket, keep, prefix=""):
    """Drop the oldest archives once there are more than `keep` of them."""

    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = response.get("Contents", [])

    if len(objects) <= keep:
        return 0

    objects.sort(key=lambda item: item["LastModified"])
    stale = objects[: len(objects) - keep]

    client.delete_objects(
        Bucket=bucket,
        Delete={"Objects": [{"Key": item["Key"]} for item in stale]},
    )
    return len(stale)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=int, default=30,
                        help="how many archives to keep in the bucket")
    args = parser.parse_args()

    archive = newest_archive()
    if archive is None:
        raise SystemExit("ما في نسخة احتياطية للرفع")

    client, bucket, prefix = _client()
    key = prefix + os.path.basename(archive)
    size_mb = os.path.getsize(archive) / (1024 * 1024)

    client.upload_file(archive, bucket, key)
    print(f"✓ رُفعت: {bucket}/{key}  ({size_mb:.1f} ميجا)")

    removed = prune(client, bucket, args.keep, prefix)
    if removed:
        print(f"  حُذفت {removed} نسخة قديمة (الاحتفاظ بآخر {args.keep})")


if __name__ == "__main__":
    main()
