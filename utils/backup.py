import os
import json
import logging
import zipfile
import shutil
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.inspection import inspect
from models import db
from datetime import datetime, date

logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================

BACKUP_FOLDER = "backups"
UPLOAD_FOLDER = "uploads"
TEMP_FOLDER = "backup_temp"
MAX_BACKUPS = 10


# =========================
# HELPERS
# =========================

def ensure_directories():
    os.makedirs(BACKUP_FOLDER, exist_ok=True)


def get_all_tables():
    inspector = inspect(db.engine)
    return inspector.get_table_names()


# =========================
# EXPORT DATABASE
# =========================



def export_database(export_dir):
    logger.info("Backup export started")
    os.makedirs(export_dir, exist_ok=True)

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    for table in tables:
        try:
            result = db.session.execute(text(f'SELECT * FROM "{table}"'))
            rows = [dict(r._mapping) for r in result]

            logger.info("Exported table %s: %s rows", table, len(rows))

            with open(os.path.join(export_dir, f"{table}.json"), "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=4, default=str)

        except Exception:
            logger.exception("Failed to export table %s", table)
            raise


# =========================
# EXPORT FILES (uploads)
# =========================

def export_uploads(temp_dir):

    uploads_dst = os.path.join(temp_dir, "uploads")

    logger.info("Exporting uploads (source exists: %s)", os.path.exists(UPLOAD_FOLDER))

    if os.path.exists(UPLOAD_FOLDER):
        shutil.copytree(UPLOAD_FOLDER, uploads_dst, dirs_exist_ok=True)


def restore_uploads(temp_dir):

    uploads_src = os.path.join(temp_dir, "uploads")

    if os.path.exists(uploads_src):
        shutil.copytree(uploads_src, UPLOAD_FOLDER, dirs_exist_ok=True)


# =========================
# METADATA
# =========================

def create_metadata(temp_dir):
    metadata = {
        "created_at": datetime.now().isoformat(),
        "project": "warehouse_system"
    }

    with open(os.path.join(temp_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=4)


# =========================
# ZIP BACKUP
# =========================

def zip_backup(temp_dir):
    ensure_directories()

    backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    backup_path = os.path.join(BACKUP_FOLDER, backup_name)

    # ZIP CREATION
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:

        for root, _, files in os.walk(temp_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, temp_dir)
                zipf.write(full_path, arcname)

    return backup_name


# =========================
# MAIN FUNCTION
# =========================

def create_backup_zip():
    logger.info("Creating backup zip")
    temp_dir = os.path.join(
        TEMP_FOLDER,
        f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # IMPORTANT: create structure first
    data_dir = os.path.join(temp_dir, "data")
    uploads_dir = os.path.join(temp_dir, "uploads")

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(uploads_dir, exist_ok=True)

    # 1. export DB
    export_database(data_dir)

    # 2. export uploads
    export_uploads(temp_dir)

    # 3. metadata
    create_metadata(temp_dir)

    # 4. zip
    backup_name = zip_backup(temp_dir)

    # 5. cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)

    # 6. cleanup old backups
    cleanup_old_backups()

    return backup_name


# =========================
# CLEAN OLD BACKUPS
# =========================

def cleanup_old_backups():

    files = sorted(
        [
            f for f in os.listdir(BACKUP_FOLDER)
            if f.endswith(".zip")
        ],
        key=lambda x: os.path.getmtime(os.path.join(BACKUP_FOLDER, x))
    )

    while len(files) > MAX_BACKUPS:
        os.remove(os.path.join(BACKUP_FOLDER, files[0]))
        files.pop(0)


# =========================
# LIST BACKUPS
# =========================

def get_backup_files(folder=BACKUP_FOLDER):

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

    files.sort(key=lambda x: x["date"], reverse=True)

    return files


def clear_database():
    tables = get_all_tables()

    db.session.execute(text("SET session_replication_role = replica;"))

    try:
        for table in tables:
            db.session.execute(
                text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
            )

        db.session.commit()

    finally:
        db.session.execute(text("SET session_replication_role = DEFAULT;"))
        db.session.commit()


def restore_table(table_name, data_dir):

    json_file = os.path.join(data_dir, f"{table_name}.json")

    if not os.path.exists(json_file):
        return

    with open(json_file, encoding="utf-8") as f:
        rows = json.load(f)

    if not rows:
        return

    for row in rows:

        columns = list(row.keys())

        column_names = ", ".join(f'"{c}"' for c in columns)

        placeholders = ", ".join(f":{c}" for c in columns)

        sql = text(f"""
            INSERT INTO "{table_name}"
            ({column_names})
            VALUES ({placeholders})
        """)

        db.session.execute(sql, row) 

def restore_database(data_dir):

    clear_database()

    tables = [table.name for table in reversed(db.metadata.sorted_tables)]

    db.session.execute(text("SET session_replication_role = replica;"))

    try:

        for table in tables:
            restore_table(table, data_dir)

        db.session.commit()

    finally:

        db.session.execute(text("SET session_replication_role = DEFAULT;"))
        db.session.commit()

    reset_sequences()

def reset_sequences():

    inspector = inspect(db.engine)

    tables = inspector.get_table_names()

    for table in tables:

        columns = inspector.get_columns(table)

        has_id = any(col["name"] == "id" for col in columns)

        if not has_id:
            continue

        db.session.execute(text(f"""
            SELECT setval(
                pg_get_serial_sequence('"{table}"','id'),
                COALESCE(MAX(id),1),
                true
            )
            FROM "{table}";
        """))

    db.session.commit()