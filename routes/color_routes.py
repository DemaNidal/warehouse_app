from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

from models import db, Color, Product
from flask_login import current_user, login_required
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.color import validate_color_name
from sqlalchemy.exc import IntegrityError

def register_color_routes(app):

    # =========================
    # ADD + LIST
    # =========================
    @app.route("/add-color", methods=["GET", "POST"])
    @login_required
    @manager_required
    def add_color():

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if not ensure_system_ready():
            if is_ajax:
                return jsonify(success=False, message="النظام قيد الاسترجاع حالياً"), 503
            return redirect(url_for("dashboard"))

        if request.method == "POST":

            result = validate_color_name(request.form.get("name", ""))

            if not result.valid:
                if is_ajax:
                    return jsonify(success=False, message=result.message), 400
                flash(result.message, "danger")
                return redirect(url_for("add_color"))

            name = result.data

            exists = Color.query.filter_by(name=name).first()
            if exists:
                if is_ajax:
                    return jsonify(success=False, message="هذا اللون موجود مسبقاً"), 409
                flash("هذا اللون موجود مسبقاً", "warning")
                return redirect(url_for("add_color"))

            color = Color(name=name)

            try:
                db.session.add(color)
                db.session.commit()

                log_activity(
                    current_user.id,
                    "ADD_COLOR",
                    f"اضافة اللون: {color.name}"
                )

                if is_ajax:
                    return jsonify(success=True, id=color.id, name=color.name)

                flash("تمت إضافة اللون بنجاح", "success")

            except IntegrityError:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="هذا اللون موجود مسبقاً"), 409
                flash("هذا اللون موجود مسبقاً (DB)", "warning")

            except Exception:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="حدث خطأ أثناء الحفظ"), 500
                flash("حدث خطأ أثناء الحفظ", "danger")

            return redirect(url_for("add_color"))

        colors = Color.query.order_by(Color.id.desc()).all()
        return render_template("add_color.html", colors=colors)


    # =========================
    # EDIT (MODAL)
    # =========================
    @app.route("/color/<int:color_id>/edit", methods=["POST"])
    @login_required
    @admin_required
    def edit_color(color_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        color = Color.query.get_or_404(color_id)

        result = validate_color_name(request.form.get("name", ""))

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("add_color"))

        name = result.data

        exists = Color.query.filter(
            Color.name == name,
            Color.id != color.id
        ).first()

        if exists:
            flash("هذا اللون موجود مسبقاً", "warning")
            return redirect(url_for("add_color"))

        color.name = name
        db.session.commit()
        log_activity(
            current_user.id,
            "EDIT_COLOR",
            f"تعديل اللون: {color.name}"
        )

        flash("تم تعديل اللون بنجاح", "success")
        return redirect(url_for("add_color"))


    # =========================
    # DELETE
    # =========================
    @app.route("/color/<int:color_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_color(color_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        color = Color.query.get_or_404(color_id)

        in_use = Product.query.filter_by(color_id=color.id).first() is not None

        if in_use:
            flash("لا يمكن حذف لون مستخدم في منتجات", "danger")
            return redirect(url_for("add_color"))

        name = color.name

        db.session.delete(color)
        db.session.commit()

        log_activity(
            current_user.id,
            "DELETE_COLOR",
            f"حذف اللون: {name}"
        )

        flash("تم حذف اللون بنجاح", "success")
        return redirect(url_for("add_color"))


