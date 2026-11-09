from flask import render_template, request
from flask_login import login_required

from models import db, ActivityLog, User
from utils.permissions import admin_required
from utils.clock import local_day_bounds

from sqlalchemy.orm import joinedload

def register_activity_routes(app):

    @app.route("/activity-logs")
    @login_required
    @admin_required
    def activity_logs():

        page = request.args.get("page", 1, type=int)
        q = request.args.get("q", "").strip()
        user_id = request.args.get("user", type=int)
        action = request.args.get("action", "").strip()
        date = request.args.get("date", "")

        query = ActivityLog.query.options(joinedload(ActivityLog.user))

        if q:
            query = query.filter(ActivityLog.description.ilike(f"%{q}%"))

        if user_id:
            query = query.filter(ActivityLog.user_id == user_id)

        if action:
            query = query.filter(ActivityLog.action == action)

        if date:
            bounds = local_day_bounds(date)

            if bounds is None:
                date = ""
            else:
                # created_at holds UTC; the box holds a local day.
                day_start, day_end = bounds
                query = query.filter(
                    ActivityLog.created_at >= day_start,
                    ActivityLog.created_at < day_end
                )

        logs = query.order_by(ActivityLog.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False, max_per_page=100
        )

        users = User.query.order_by(User.username).all()

        actions = [
            row[0] for row in
            db.session.query(ActivityLog.action).distinct().order_by(ActivityLog.action).all()
        ]

        return render_template(
            "activity_logs.html",
            logs=logs,
            users=users,
            actions=actions,
            q=q,
            user_id=user_id,
            action=action,
            date=date
        )
