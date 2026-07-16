from flask import (
    render_template,
    redirect,
    url_for,
    abort,
    request,
    flash
)

from flask_login import (
    login_required,
    current_user
)

from models import (
    db,
    Notification
)
from sqlalchemy.orm import joinedload


def register_notifications_routes(app):

    @app.route("/notifications")
    @login_required
    def notifications():

        filter_type = request.args.get("filter", "")

        page = request.args.get("page", 1, type=int)

        query = Notification.query.options(
            joinedload(Notification.product)
        ).filter_by(
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

        pagination = query.order_by(
            Notification.created_at.desc()
        ).paginate(
            page=page,
            per_page=20,
            error_out=False
        )

        unread_count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()

        return render_template(
            "notifications.html",
            notifications=pagination.items,
            pagination=pagination,
            filter_type=filter_type,
            unread_count=unread_count
        )

    @app.route("/notifications/mark-all-read", methods=["POST"])
    @login_required
    def mark_all_notifications_read():

        Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).update({"is_read": True})

        db.session.commit()

        flash("تم تحديد جميع الإشعارات كمقروءة", "success")

        return redirect(url_for(
            "notifications",
            filter=request.form.get("filter") or None
        ))

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