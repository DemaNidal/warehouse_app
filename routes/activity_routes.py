from flask import render_template, request
from flask_login import login_required

from models import ActivityLog
from utils.permissions import admin_required

from sqlalchemy.orm import joinedload

def register_activity_routes(app):

    @app.route("/activity-logs")
    @login_required
    @admin_required
    def activity_logs():

        page = request.args.get(
            "page",
            1,
            type=int
        )
        logs = (
            ActivityLog.query
            .options(joinedload(ActivityLog.user))
            .order_by(ActivityLog.created_at.desc())
            .paginate(page=page, per_page=50, error_out=False, max_per_page=100)
        )

        return render_template(
            "activity_logs.html",
            logs=logs
        )