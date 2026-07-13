from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from flask_login import login_required, current_user

from models import db, User
from utils.activity_logger import log_activity
from utils.permissions import admin_required
from utils.system_guard import ensure_system_ready
from utils.validation.user import validate_add_user, validate_edit_user, validate_password
from sqlalchemy.exc import IntegrityError


def register_user_routes(app):

    @app.route("/profile")
    @login_required
    def profile():
        return render_template("profile.html", user=current_user)

    @app.route("/users")
    @login_required
    @admin_required
    def user_list():

        q = request.args.get("q", "").strip()

        page = request.args.get("page", 1, type=int)

        query = User.query.order_by(User.id.desc())

        if q:
            query = query.filter(User.username.ilike(f"%{q}%"))

        pagination = query.paginate(
            page=page,
            per_page=20,
            error_out=False
        )

        total_count = User.query.count()

        active_count = User.query.filter_by(is_active_user=True).count()

        disabled_count = total_count - active_count

        return render_template(
            "users.html",
            users=pagination.items,
            pagination=pagination,
            q=q,
            total_count=total_count,
            active_count=active_count,
            disabled_count=disabled_count
        )

    @app.route("/user/add", methods=["GET", "POST"])
    @login_required
    @admin_required
    def add_user():

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        if request.method == "POST":

            result = validate_add_user(
                request.form.get("username", ""),
                request.form.get("password", ""),
                request.form.get("confirm_password", ""),
                request.form.get("role", "")
            )

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("add_user"))

            data = result.data

            exists = User.query.filter_by(username=data["username"]).first()

            if exists:
                flash("اسم المستخدم موجود", "danger")
                return redirect(url_for("add_user"))

            user = User(
                username=data["username"],
                role=data["role"]
            )

            user.set_password(data["password"])

            try:
                db.session.add(user)
                db.session.commit()

            except IntegrityError:
                db.session.rollback()
                flash("اسم المستخدم موجود", "danger")
                return redirect(url_for("add_user"))

            log_activity(
                current_user.id,
                "ADD_USER",
                f"اضافة المستخدم: {user.username}"
            )

            flash("تم إنشاء المستخدم", "success")

            return redirect(url_for("user_list"))

        return render_template("add_user.html")
    
    @app.route("/user/<int:user_id>/disable", methods=["POST"])
    @login_required
    @admin_required
    def disable_user(user_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        user = User.query.get_or_404(user_id)

        if user.id == current_user.id:
            flash("لا يمكنك تعطيل حسابك", "danger")
            return redirect(url_for("user_list"))

        user.is_active_user = False
        db.session.commit()

        log_activity(
            current_user.id,
            "DISABLE_USER",
            f"تعطيل المستخدم: {user.username}"
        )

        flash("تم تعطيل المستخدم", "success")

        return redirect(url_for("user_list"))
    

    @app.route("/user/<int:user_id>/enable", methods=["POST"])
    @login_required
    @admin_required
    def enable_user(user_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        user = User.query.get_or_404(user_id)

        user.is_active_user = True
        db.session.commit()

        log_activity(
            current_user.id,
            "ENABLE_USER",
            f"تفعيل المستخدم: {user.username}"
        )

        flash("تم تفعيل المستخدم", "success")

        return redirect(url_for("user_list"))


    @app.route("/user/<int:user_id>/edit", methods=["GET", "POST"])
    @login_required
    @admin_required
    def edit_user(user_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        user = User.query.get_or_404(user_id)

        if request.method == "POST":

            result = validate_edit_user(
                request.form.get("username", ""),
                request.form.get("role", "")
            )

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("edit_user", user_id=user.id))

            data = result.data

            if user.id == current_user.id and data["role"] != user.role:
                flash("لا يمكنك تغيير صلاحيتك الخاصة", "danger")
                return redirect(url_for("edit_user", user_id=user.id))

            exists = User.query.filter(
                User.username == data["username"],
                User.id != user.id
            ).first()

            if exists:
                flash("اسم المستخدم موجود مسبقاً", "danger")
                return redirect(url_for("edit_user", user_id=user.id))

            user.username = data["username"]
            user.role = data["role"]

            db.session.commit()

            log_activity(
                current_user.id,
                "EDIT_USER",
                f"تعديل المستخدم: {user.username}"
            )

            flash("تم تعديل المستخدم", "success")

            return redirect(url_for("user_list"))

        return render_template("edit_user.html", user=user)


    @app.route("/profile/change-password", methods=["GET", "POST"])
    @login_required
    def change_password():

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        if request.method == "POST":

            current_password = request.form["current_password"]
            new_password = request.form["new_password"]
            confirm_password = request.form["confirm_password"]

            if not current_user.check_password(current_password):
                flash("كلمة المرور الحالية غير صحيحة", "danger")
                return redirect(url_for("change_password"))

            if new_password != confirm_password:
                flash("تأكيد كلمة المرور غير متطابق", "danger")
                return redirect(url_for("change_password"))

            current_user.set_password(new_password)
            db.session.commit()

            log_activity(
                current_user.id,
                "CHANGE_PASSWORD",
                f"المستخدم {current_user.username} قام بتغيير كلمة المرور الخاصة به"
            )

            flash("تم تغيير كلمة المرور", "success")

            return redirect(url_for("profile"))

        return render_template("change_password.html")


    @app.route("/user/<int:user_id>/reset-password", methods=["GET", "POST"])
    @login_required
    @admin_required
    def reset_user_password(user_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        user = User.query.get_or_404(user_id)

        if request.method == "POST":

            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            password_result = validate_password(new_password)

            if not password_result.valid:
                flash(password_result.message, "danger")
                return redirect(url_for("reset_user_password", user_id=user.id))

            if new_password != confirm_password:
                flash("كلمتا المرور غير متطابقتين", "danger")
                return redirect(url_for("reset_user_password", user_id=user.id))

            user.set_password(new_password)
            db.session.commit()

            log_activity(
                current_user.id,
                "RESET_PASSWORD",
                f"إعادة تعيين كلمة المرور لـ: {user.username}"
            )

            flash("تم إعادة تعيين كلمة المرور", "success")

            return redirect(url_for("user_list"))

        return render_template("reset_user_password.html", user=user)