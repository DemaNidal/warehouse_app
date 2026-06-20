import datetime
import os
import zipfile

from utils.activity_logger import log_activity

from flask import (
    redirect,
    url_for,
    flash
)

from flask_login import (
    current_user
)
from datetime import datetime

def create_backup_zip():
    import os, zipfile
    from datetime import datetime

    os.makedirs("backups", exist_ok=True)

    backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    backup_path = os.path.join("backups", backup_name)

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:

        zipf.write("instance/warehouse.db", arcname="warehouse.db")

        for root, dirs, files in os.walk("uploads"):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, ".")
                zipf.write(full_path, arcname)

    # keep last 10 backups
    files = sorted(
        [f for f in os.listdir("backups") if f.endswith(".zip")],
        key=lambda x: os.path.getmtime(os.path.join("backups", x))
    )

    while len(files) > 10:
        os.remove(os.path.join("backups", files[0]))
        files.pop(0)

    return backup_name


def get_backup_files(folder="backups"):
    os.makedirs(folder, exist_ok=True)

    files = []

    for filename in os.listdir(folder):

        if not filename.endswith(".zip"):
            continue

        filepath = os.path.join(folder, filename)

        files.append({
            "name": filename,
            "size": round(os.path.getsize(filepath) / 1024, 2),
            "date": datetime.fromtimestamp(os.path.getmtime(filepath))
        })

    # sort newest first
    files.sort(key=lambda x: x["date"], reverse=True)

    return files