from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

from flask_login import (
    login_user,
    logout_user,
    login_required
)

from models import User


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

                session.permanent = True

                login_user(user)

                return redirect(
                    "/dashboard"
                )

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

        logout_user()

        return redirect(
            url_for("login")
        )