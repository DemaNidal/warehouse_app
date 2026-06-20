from flask import (
    abort,
    render_template,
    redirect,
    request,
    send_file,
    url_for,
    flash
)

from flask_login import (
    login_required,
    current_user
)


from utils.backup import create_backup_zip, get_backup_files
from utils.permissions import (
    admin_required
)

from utils.activity_logger import (
    log_activity
)

import os
import shutil
import uuid

from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
import zipfile
from config import RESTORE_SECRET, RESTORE_IN_PROGRESS
RESTORE_IN_PROGRESS = False  # put this at top of your file

def register_backup_routes(app):

    @app.route("/backups")
    @login_required
    @admin_required
    def backups():

        files = get_backup_files()

        return render_template(
            "backups.html",
            files=files
        )



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
        
        return send_file(
            os.path.join(
                "backups",
                filename
            ),
            as_attachment=True
        )
    
    @app.route(
    "/backup/delete/<filename>",
    methods=["POST"]
    )
    @login_required
    @admin_required
    def delete_backup(filename):
        filename = secure_filename(filename)
        filepath = os.path.join("backups", filename)

        if not os.path.isfile(filepath):
            abort(404)
        filepath = os.path.join(
            "backups",
            filename
        )

        if os.path.exists(filepath):

            os.remove(filepath)

            log_activity(
                current_user.id,
                f"DELETE_BACKUP | {filename}"
            )

            flash(
                "تم حذف النسخة الاحتياطية",
                "success"
            )

        return redirect(
            url_for("backups")
        )
    


    @app.route("/backup/restore", methods=["POST"])
    @admin_required
    def restore_backup():
        global RESTORE_IN_PROGRESS

        # ==============================
        # 0. DEVELOPER SECRET CHECK
        # ==============================
        secret = request.form.get("restore_secret")

        if not secret:
            flash("Restore secret is required", "danger")
            return redirect(url_for("backups"))

        if secret != RESTORE_SECRET:
            flash("Invalid restore secret", "danger")
            return redirect(url_for("backups"))

        file = request.files.get("backup_file")

        if not file or not file.filename.endswith(".zip"):
            flash("Invalid backup file", "danger")
            return redirect(url_for("backups"))

        backup_path = os.path.join("backups", file.filename)
        file.save(backup_path)

        temp_dir = "restore_temp"

        shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)

        with zipfile.ZipFile(backup_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        db_file = os.path.join(temp_dir, "warehouse.db")
        uploads_dir = os.path.join(temp_dir, "uploads")

        # ==============================
        # 1. BACKUP INTEGRITY CHECK
        # ==============================
        if not os.path.exists(db_file):
            flash("Backup invalid: database not found", "danger")
            return redirect(url_for("backups"))

        # ==============================
        # 2. LOCK SYSTEM
        # ==============================
        RESTORE_IN_PROGRESS = True

        try:
            # ==============================
            # 3. ROLLBACK BACKUP
            # ==============================
            db_path = os.path.join("instance", "warehouse.db")

            if os.path.exists(db_path):
                rollback_name = f"backup_before_restore_{uuid.uuid4().hex}.db"
                shutil.copy2(db_path, rollback_name)

            # restore database
            os.makedirs("backups/rollback", exist_ok=True)

            rollback_name = os.path.join(
                "backups",
                "rollback",
                f"backup_before_restore_{uuid.uuid4().hex}.db"
            )

            shutil.copy2(db_path, rollback_name)

            # optional uploads restore
            if os.path.exists(uploads_dir):
                if os.path.exists("uploads"):
                    shutil.rmtree("uploads", ignore_errors=True)
                shutil.copytree(uploads_dir, "uploads")

            flash("Database restored successfully", "success")

        except Exception as e:
            flash(f"Restore failed: {str(e)}", "danger")

        finally:
            RESTORE_IN_PROGRESS = False

        return redirect(url_for("backups"))