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


def register_auth_routes(app):

    @app.route(
        "/login",
        methods=["GET", "POST"]
    )
    def login():

        if request.method == "POST":

            username = request.form["username"]
            password = request.form["password"]

            user = User.query.filter_by(
                username=username
            ).first()

            if (
                user and
                user.check_password(password)
            ):

                if not user.is_active_user:

                    flash(
                        "الحساب معطل",
                        "danger"
                    )

                    return redirect(
                        url_for("login")
                    )

                session.permanent = True

                login_user(user)

                log_activity(
                    user.id,
                    "LOGIN",
                    "User logged in"
                )

                return redirect("/dashboard")

            flash(
                "بيانات الدخول غير صحيحة",
                "danger"
            )

        return render_template(
            "login.html"
        )

    @app.route("/logout")
    @login_required
    def logout():

        user_id = current_user.id
        username = current_user.username

        log_activity(
            user_id,
            "LOGOUT",
            f"User {username} logged out"
        )

        logout_user()

        return redirect(
            url_for("login")
        )