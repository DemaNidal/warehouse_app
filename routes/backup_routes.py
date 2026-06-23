from flask import (
    abort,
    render_template,
    redirect,
    request,
    send_file,
    url_for,
    flash
)

from flask_login import login_required, current_user

from utils.backup import create_backup_zip, get_backup_files
from utils.permissions import admin_required
from utils.activity_logger import log_activity

import os
import shutil
import uuid
import zipfile

from werkzeug.utils import secure_filename

from config import RESTORE_SECRET
import config

from models import db
from utils.validation.backup import validate_restore


def register_backup_routes(app):

    @app.route("/backups")
    @login_required
    @admin_required
    def backups():
        files = get_backup_files()
        return render_template("backups.html", files=files)


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

        flash("تم إنشاء نسخة ZIP احتياطية", "success")
        return redirect(url_for("backups"))


    @app.route("/backup/download/<filename>")
    @login_required
    @admin_required
    def download_backup(filename):

        filename = secure_filename(filename)
        filepath = os.path.join("backups", filename)

        if not os.path.isfile(filepath):
            abort(404)

        return send_file(filepath, as_attachment=True)


    @app.route("/backup/delete/<filename>", methods=["POST"])
    @login_required
    @admin_required
    def delete_backup(filename):

        filename = secure_filename(filename)
        filepath = os.path.join("backups", filename)

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


    @app.route("/backup/restore", methods=["POST"])
    @login_required
    @admin_required
    def restore_backup():

        result = validate_restore(
            request.form.get("restore_secret"),
            request.files.get("backup_file"),
            RESTORE_SECRET
        )

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("backups"))
        secret = request.form.get("restore_secret")
        file = request.files.get("backup_file")

        result = validate_restore(
            secret,
            file,
            RESTORE_SECRET
        )

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("backups"))

        # secure temp zip
        temp_zip_path = os.path.join(
            "backups",
            f"{uuid.uuid4().hex}.zip"
        )
        file.save(temp_zip_path)

        temp_dir = "restore_temp"
        shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)

        with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        db_file = os.path.join(temp_dir, "warehouse.db")
        uploads_dir = os.path.join(temp_dir, "uploads")

        if not os.path.exists(db_file):
            flash("Backup invalid: database not found", "danger")
            return redirect(url_for("backups"))

        config.RESTORE_IN_PROGRESS = True

        try:
            # close DB connections (IMPORTANT)
            db.session.remove()
            db.engine.dispose()

            db_path = os.path.join("instance", "warehouse.db")

            # rollback current DB
            if os.path.exists(db_path):
                rollback_path = os.path.join(
                    "backups",
                    "rollback",
                    f"rollback_{uuid.uuid4().hex}.db"
                )
                os.makedirs(os.path.dirname(rollback_path), exist_ok=True)
                shutil.copy2(db_path, rollback_path)

            # 🔥 ACTUAL RESTORE (FIXED PART)
            shutil.copy2(db_file, db_path)

            # restore uploads
            if os.path.exists(uploads_dir):
                if os.path.exists("uploads"):
                    shutil.rmtree("uploads", ignore_errors=True)
                shutil.copytree(uploads_dir, "uploads")

            log_activity(
                current_user.id,
                "RESTORE_BACKUP",
                os.path.basename(temp_zip_path)
            )

            flash("Database restored successfully", "success")

        except Exception as e:
            flash(f"Restore failed: {str(e)}", "danger")

        finally:
            config.RESTORE_IN_PROGRESS = False
            shutil.rmtree(temp_dir, ignore_errors=True)

            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)

        return redirect(url_for("backups"))