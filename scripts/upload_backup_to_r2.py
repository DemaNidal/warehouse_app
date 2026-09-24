# -*- coding: utf-8 -*-
"""Copy the newest backup archive into object storage.

A backup that lives on the same disk as the database is not a backup. It
survives a mistaken delete and nothing else — not a failed disk, not a
cancelled server, not a provider account problem. This puts the archive
somewhere with no shared failure mode, under the `backups/` prefix of the
bucket the product images already use.

    python scripts/upload_backup_to_r2.py             # newest archive
    python scripts/upload_backup_to_r2.py --keep 30   # and prune older ones
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PREFIX = "backups/"


def _client():
    """The same R2 credentials the image storage uses."""

    import boto3
    from botocore.config import Config

    # the same two spellings utils.storage accepts, so one .env serves both
    account = os.getenv("R2_ACCOUNT_ID", "").strip()
    endpoint = os.getenv("R2_ENDPOINT", "").strip() or (
        f"https://{account}.r2.cloudflarestorage.com" if account else ""
    )

    missing = [
        name for name in
        ("R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
        if not os.getenv(name)
    ]
    if not endpoint:
        missing.append("R2_ACCOUNT_ID (أو R2_ENDPOINT)")

    if missing:
        raise SystemExit("ناقص إعدادات R2: " + "، ".join(missing))

    session = boto3.session.Session()
    client = session.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )
    return client, os.environ["R2_BUCKET"]


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


def prune(client, bucket, keep):
    """Drop the oldest archives once there are more than `keep` of them."""

    response = client.list_objects_v2(Bucket=bucket, Prefix=PREFIX)
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

    client, bucket = _client()
    key = PREFIX + os.path.basename(archive)
    size_mb = os.path.getsize(archive) / (1024 * 1024)

    client.upload_file(archive, bucket, key)
    print(f"✓ رُفعت: {key}  ({size_mb:.1f} ميجا)")

    removed = prune(client, bucket, args.keep)
    if removed:
        print(f"  حُذفت {removed} نسخة قديمة (الاحتفاظ بآخر {args.keep})")


if __name__ == "__main__":
    main()
