from flask import (
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
from utils.backup import create_backup_zip, get_backup_files
from utils.permissions import admin_required
from utils.activity_logger import log_activity
from utils.validation.backup import validate_restore
import config


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

        backup_name = create_backup_zip()

        log_activity(
            current_user.id,
            "CREATE_BACKUP",
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
            "DELETE_BACKUP",
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

        try:
            # extract
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                zip_ref.extractall(TEMP_DIR)

            db_file = os.path.join(TEMP_DIR, "warehouse.db")
            uploads_dir = os.path.join(TEMP_DIR, "uploads")

            if not os.path.exists(db_file):
                flash("Invalid backup file", "danger")
                return redirect(url_for("backups"))

            # stop DB connections
            db.session.remove()
            db.engine.dispose()

            # backup current DB (rollback safety)
            if os.path.exists(DB_PATH):
                rollback_dir = os.path.join(BACKUP_FOLDER, "rollback")
                os.makedirs(rollback_dir, exist_ok=True)

                shutil.copy2(
                    DB_PATH,
                    os.path.join(
                        rollback_dir,
                        f"rollback_{uuid.uuid4().hex}.db"
                    )
                )

            # restore DB
            shutil.copy2(db_file, DB_PATH)

            # restore uploads
            if os.path.exists(uploads_dir):
                shutil.rmtree(UPLOAD_FOLDER, ignore_errors=True)
                shutil.copytree(uploads_dir, UPLOAD_FOLDER)

            log_activity(
                current_user.id,
                "RESTORE_BACKUP",
                os.path.basename(temp_zip_path)
            )

            flash("تم استرجاع النسخة بنجاح", "success")

        except Exception as e:
            flash(f"فشل الاسترجاع: {str(e)}", "danger")

        finally:
            shutil.rmtree(TEMP_DIR, ignore_errors=True)

            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)

        return redirect(url_for("backups"))