import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    filename=os.path.join(os.path.dirname(__file__), "backup_task.log"),
)

from app import app
from utils.backup import create_backup_zip

with app.app_context():
    try:
        name = create_backup_zip()
        logging.info("Scheduled backup created: %s", name)
        print(f"Backup created: {name}")
    except Exception:
        logging.exception("Scheduled backup failed")
        raise

# The database archive no longer carries images — they live in object storage —
# so pull a local copy of the bucket in the same nightly run. Kept separate
# from the archive above: a failure here must not lose the database backup that
# already succeeded.
if os.getenv("STORAGE_BACKEND", "local").strip().lower() != "local":
    try:
        from scripts.sync_images_backup import build_client, list_remote, _write_manifest

        storage = build_client()
        remote = list_remote(storage)

        dest = os.path.join("backups", "images")
        os.makedirs(dest, exist_ok=True)

        downloaded = 0
        for key, size in remote.items():
            path = os.path.join(dest, os.path.basename(key))
            if os.path.exists(path) and os.path.getsize(path) == size:
                continue
            storage.client.download_file(storage.bucket, key, path)
            downloaded += 1

        _write_manifest(dest, remote)

        logging.info(
            "Image backup synced: %s new, %s total in bucket", downloaded, len(remote)
        )
        print(f"Images synced: {downloaded} new, {len(remote)} total")

    except Exception:
        logging.exception("Image backup sync failed (database backup is unaffected)")
        print("Warning: image sync failed — see backup_task.log")


# Put the archive somewhere the server cannot take with it. Kept in its own
# try block for the same reason as the image sync above: an upload failure must
# not discard a backup that was written successfully.
if os.getenv("STORAGE_BACKEND", "local").strip().lower() != "local":
    try:
        from scripts.upload_backup_to_r2 import (
            _client,
            newest_archive,
            prune,
            PREFIX,
        )

        archive = newest_archive()
        if archive is None:
            raise RuntimeError("no archive to upload")

        client, bucket = _client()
        client.upload_file(archive, bucket, PREFIX + os.path.basename(archive))
        removed = prune(client, bucket, 30)

        logging.info(
            "Backup archive uploaded to object storage: %s (%s old removed)",
            os.path.basename(archive), removed,
        )
        print(f"Archive uploaded off-server: {os.path.basename(archive)}")

    except Exception:
        logging.exception(
            "Off-server backup upload failed (the local archive is unaffected)"
        )
        print("Warning: off-server upload failed — see backup_task.log")
