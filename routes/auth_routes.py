from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

from flask_login import (
    current_user,
    login_user,
    logout_user,
    login_required
)

from models import User
from utils.activity_logger import log_activity
from utils.validation.auth import validate_login
from extensions import limiter


def register_auth_routes(app):

    @app.route("/login", methods=["GET", "POST"])
    # Only the attempts are limited. The limit used to cover the route, so
    # merely opening the page five times — a refresh, a mistyped password, the
    # back button — locked the door for a minute with an English error page.
    # The hourly cap is what actually stops guessing; the per-minute one just
    # keeps a wrong password from being hammered.
    @limiter.limit("10 per minute; 60 per hour", methods=["POST"])
    def login():

        if request.method == "POST":

            result = validate_login(
                request.form.get("username", ""),
                request.form.get("password", "")
            )

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("login"))

            data = result.data

            user = User.query.filter_by(
                username=data["username"]
            ).first()

            if user and user.check_password(data["password"]):

                if not user.is_active_user:
                    flash("الحساب معطل", "danger")
                    return redirect(url_for("login"))

                # Drop whatever the visitor's session held before they
                # authenticated, so a value planted beforehand cannot ride
                # along into the logged-in session (session fixation).
                session.clear()

                # PERMANENT_SESSION_LIFETIME (8 hours) does nothing unless the
                # session is marked permanent — without this the cookie dies
                # with the browser and everyone signs in again each morning.
                session.permanent = True

                login_user(user)

                log_activity(
                    user.id,
                    "LOGIN",
                    "تسجيل الدخول إلى النظام"
                )

                if user.role in ["ADMIN", "STORE_MANAGER"]:
                    return redirect(url_for("dashboard"))

                return redirect(url_for("home"))

            flash("بيانات الدخول غير صحيحة", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():

        log_activity(
            current_user.id,
            "LOGOUT",
            f"قام المستخدم {current_user.username} بتسجيل الخروج"
        )

        logout_user()

        return redirect(url_for("login"))