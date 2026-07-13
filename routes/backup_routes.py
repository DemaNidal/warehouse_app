from flask import (
    current_app,
    render_template,
    redirect,
    request,
    send_file,
    url_for,
    flash,
    abort
)

from flask_login import login_required, current_user

import os
import shutil
import uuid
import zipfile

from werkzeug.utils import secure_filename

from models import db
from utils.backup import (
    create_backup_zip,
    get_backup_files,
    restore_database,
    restore_uploads
)
from utils.permissions import admin_required
from utils.activity_logger import log_activity
from utils.validation.backup import validate_restore
import config


def _safe_extract(zip_ref, target_dir):
    target_root = os.path.realpath(target_dir)

    for name in zip_ref.namelist():
        resolved = os.path.realpath(os.path.join(target_dir, name))

        if resolved != target_root and not resolved.startswith(target_root + os.sep):
            raise ValueError(f"Unsafe path in backup archive: {name}")

    zip_ref.extractall(target_dir)


BACKUP_FOLDER = "backups"
UPLOAD_FOLDER = "uploads"
DB_PATH = os.path.join("instance", "warehouse.db")
TEMP_DIR = "restore_temp"


def register_backup_routes(app):

    # =========================
    # LIST BACKUPS
    # =========================
    @app.route("/backups")
    @login_required
    @admin_required
    def backups():
        files = get_backup_files()
        return render_template("backups.html", files=files)


    # =========================
    # CREATE BACKUP
    # =========================
    @app.route("/backup/create", methods=["POST"])
    @login_required
    @admin_required
    def create_backup():

        try:
            backup_name = create_backup_zip()

        except Exception:
            current_app.logger.exception("Backup creation failed")
            flash("فشل إنشاء النسخة الاحتياطية", "danger")
            return redirect(url_for("backups"))

        log_activity(
            current_user.id,
            "انشاء نسخة احتياطية",
            backup_name
        )

        flash("تم إنشاء نسخة احتياطية بنجاح", "success")
        return redirect(url_for("backups"))


    # =========================
    # DOWNLOAD BACKUP
    # =========================
    @app.route("/backup/download/<filename>")
    @login_required
    @admin_required
    def download_backup(filename):

        filename = secure_filename(filename)
        filepath = os.path.join(BACKUP_FOLDER, filename)

        if not os.path.isfile(filepath):
            abort(404)

        return send_file(filepath, as_attachment=True)


    # =========================
    # DELETE BACKUP
    # =========================
    @app.route("/backup/delete/<filename>", methods=["POST"])
    @login_required
    @admin_required
    def delete_backup(filename):

        filename = secure_filename(filename)
        filepath = os.path.join(BACKUP_FOLDER, filename)

        if not os.path.isfile(filepath):
            abort(404)

        os.remove(filepath)

        log_activity(
            current_user.id,
            "حذف نسخة احتياطية",
            filename
        )

        flash("تم حذف النسخة الاحتياطية", "success")
        return redirect(url_for("backups"))


    # =========================
    # RESTORE BACKUP
    # =========================
    @app.route("/backup/restore", methods=["POST"])
    @login_required
    @admin_required
    def restore_backup():

        secret = request.form.get("restore_secret")
        file = request.files.get("backup_file")

        result = validate_restore(secret, file, config.RESTORE_SECRET)

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("backups"))

        temp_zip_path = os.path.join(
            BACKUP_FOLDER,
            f"{uuid.uuid4().hex}.zip"
        )

        file.save(temp_zip_path)

        # clean temp
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        os.makedirs(TEMP_DIR, exist_ok=True)

        config.RESTORE_IN_PROGRESS = True

        try:

            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                _safe_extract(zip_ref, TEMP_DIR)

            data_dir = os.path.join(TEMP_DIR, "data")

            if not os.path.isdir(data_dir):
                flash("Invalid backup file.", "danger")
                return redirect(url_for("backups"))

            db.session.remove()
            db.engine.dispose()

            restore_database(data_dir)

            restore_uploads(TEMP_DIR)

            log_activity(
                current_user.id,
                "استرجاع نسخة احتياطية",
                file.filename
            )

            flash("تم استرجاع النسخة الاحتياطية بنجاح", "success")

        except Exception:

            db.session.rollback()

            current_app.logger.exception("Restore failed")

            flash("فشل استرجاع النسخة الاحتياطية", "danger")

        finally:
            config.RESTORE_IN_PROGRESS = False

            shutil.rmtree(TEMP_DIR, ignore_errors=True)

            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)

        return redirect(url_for("backups"))