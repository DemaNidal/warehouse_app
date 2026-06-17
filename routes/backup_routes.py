from flask import (
    render_template,
    redirect,
    send_file,
    url_for,
    flash
)

from flask_login import (
    login_required,
    current_user
)

from utils.permissions import (
    admin_required
)

from utils.activity_logger import (
    log_activity
)

import os
import shutil

from datetime import datetime


def register_backup_routes(app):

    @app.route("/backups")
    @login_required
    @admin_required
    def backups():

        backup_folder = "backups"

        os.makedirs(
            backup_folder,
            exist_ok=True
        )

        files = []

        for filename in os.listdir(
            backup_folder
        ):

            filepath = os.path.join(
                backup_folder,
                filename
            )

            files.append({
                "name": filename,
                "size": round(
                    os.path.getsize(filepath)
                    / 1024,
                    2
                ),
                "date": datetime.fromtimestamp(
                    os.path.getmtime(filepath)
                )
            })

        files.sort(
            key=lambda x: x["date"],
            reverse=True
        )

        return render_template(
            "backups.html",
            files=files
        )


    @app.route(
        "/backup/create",
        methods=["POST"]
    )
    @login_required
    @admin_required
    def create_backup():

        os.makedirs(
            "backups",
            exist_ok=True
        )

        backup_name = (
            "warehouse_backup_"
            + datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
            + ".db"
        )

        source_db = os.path.join(
            "instance",
            "warehouse.db"
        )

        destination = os.path.join(
            "backups",
            backup_name
        )

        shutil.copy2(
            source_db,
            destination
        )

        log_activity(
            current_user.id,
            f"CREATE_BACKUP | {backup_name}"
        )

        flash(
            "تم إنشاء النسخة الاحتياطية",
            "success"
        )

        return redirect(
            url_for("backups")
        )
    
    @app.route("/backup/download/<filename>")
    @login_required
    @admin_required
    def download_backup(filename):

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