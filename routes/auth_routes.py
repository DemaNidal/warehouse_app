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


def register_auth_routes(app):

    @app.route("/login", methods=["GET", "POST"])
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

                login_user(user)

                log_activity(
                    user.id,
                    "LOGIN",
                    "User logged in"
                )

                return redirect(url_for("dashboard"))

            flash("بيانات الدخول غير صحيحة", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():

        log_activity(
            current_user.id,
            "LOGOUT",
            f"User {current_user.username} logged out"
        )

        logout_user()

        return redirect(url_for("login"))