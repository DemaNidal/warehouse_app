from flask import flash, redirect, render_template, request, url_for

from models import db, User
from utils.activity_logger import log_activity
from utils.validation.setup import validate_bootstrap_admin
from extensions import limiter
import config


def register_create_admin_route(app):

    @app.route("/bootstrap-admin", methods=["GET", "POST"])
    @limiter.limit("5 per hour")
    def bootstrap_admin():

        if User.query.filter_by(role="ADMIN").first():
            flash("تم إنشاء حساب الأدمن مسبقاً", "warning")
            return redirect(url_for("login"))

        if request.method == "POST":

            result = validate_bootstrap_admin(
                request.form.get("secret", ""),
                request.form.get("username", ""),
                request.form.get("password", ""),
                request.form.get("confirm_password", ""),
                config.BOOTSTRAP_ADMIN_SECRET
            )

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("bootstrap_admin"))

            data = result.data

            user = User(username=data["username"], role="ADMIN")
            user.set_password(data["password"])

            db.session.add(user)
            db.session.commit()

            log_activity(
                user.id,
                "BOOTSTRAP_ADMIN",
                f"تم إنشاء أول حساب أدمن: {user.username}"
            )

            flash("تم إنشاء حساب الأدمن، سجل دخولك الآن", "success")
            return redirect(url_for("login"))

        return render_template("bootstrap_admin.html")
