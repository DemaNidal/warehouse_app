from flask import (
    render_template,
    redirect,
    url_for,
    abort,
    request
)

from flask_login import (
    login_required,
    current_user
)

from models import (
    db,
    Notification
)


def register_notifications_routes(app):

    @app.route("/notifications")
    @login_required
    def notifications():

        filter_type = request.args.get("filter")

        query = Notification.query.filter_by(
            user_id=current_user.id
        )

        # unread only
        if filter_type == "unread":
            query = query.filter_by(is_read=False)

        # only alerts (NOT requests)
        elif filter_type == "alerts":
            query = query.filter(
                Notification.type.in_(["LOW", "CRITICAL"])
            )

        notifications = query.order_by(
            Notification.created_at.desc()
        ).all()

        return render_template(
            "notifications.html",
            notifications=notifications
        )

    @app.route("/notification/<int:id>/open")
    @login_required
    def open_notification(id):

        notif = Notification.query.get_or_404(id)

        if notif.user_id != current_user.id:
            abort(403)

        if not notif.is_read:
            notif.is_read = True
            db.session.commit()

        # go to target_url if exists
        if notif.target_url:
            return redirect(notif.target_url)

        # fallback to product
        if notif.product_id:
            return redirect(
                url_for("product_details", product_id=notif.product_id)
            )

        return redirect(url_for("dashboard"))