from flask import render_template
from flask_login import login_required

from models import ActivityLog
from utils.permissions import admin_required


def register_activity_routes(app):

    @app.route("/activity-logs")
    @login_required
    @admin_required
    def activity_logs():

        logs = (
            ActivityLog.query
            .order_by(
                ActivityLog.created_at.desc()
            )
            .all()
        )

        return render_template(
            "activity_logs.html",
            logs=logs
        )