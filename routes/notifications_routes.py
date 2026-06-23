from flask import (
    render_template,
    redirect,
    url_for,
    abort,
    request
)

from flask_login import login_required, current_user
from models import db, Notification


def register_notifications_routes(app):

    # =========================
    # LIST NOTIFICATIONS
    # =========================
    @app.route("/notifications")
    @login_required
    def notifications():

        filter_type = request.args.get("filter")

        query = Notification.query.filter_by(
            user_id=current_user.id
        )

        # filter: unread
        if filter_type == "unread":
            query = query.filter_by(is_read=False)

        # filter: stock type
        elif filter_type in ("LOW", "CRITICAL"):
            query = query.filter_by(type=filter_type)

        notifications = query.order_by(
            Notification.created_at.desc()
        ).all()

        return render_template(
            "notifications.html",
            notifications=notifications
        )

    # =========================
    # OPEN NOTIFICATION
    # =========================
    @app.route("/notification/<int:id>/open")
    @login_required
    def open_notification(id):

        notif = Notification.query.get_or_404(id)

        # security check
        if notif.user_id != current_user.id:
            abort(403)

        # mark as read only if needed
        if not notif.is_read:
            notif.is_read = True
            db.session.commit()

        return redirect(
            url_for(
                "product_details",
                product_id=notif.product_id
            )
        )