

from flask_login import login_required, current_user
from models import User, Notification
from flask import (
    render_template,
    redirect,
    url_for,
    abort,
    request
)
from models import db, User, Notification 
def register_notifications_routes(app):
    @app.route("/notifications")
    @login_required
    def notifications():

        filter_type = request.args.get("filter")

        query = Notification.query.filter_by(
            user_id=current_user.id
        )

        if filter_type == "unread":
            query = query.filter_by(is_read=False)

        elif filter_type in ["LOW", "CRITICAL"]:
            query = query.filter_by(type=filter_type)

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

        notif.is_read = True
        db.session.commit()

        return redirect(
            url_for("product_details", product_id=notif.product_id)
        )