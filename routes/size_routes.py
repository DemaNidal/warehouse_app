from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

from models import db, Size, Product
from flask_login import current_user, login_required
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.size import validate_size_name
from sqlalchemy.exc import IntegrityError

def register_size_routes(app):

    # =========================
    # ADD + LIST
    # =========================
    @app.route("/add-size", methods=["GET", "POST"])
    @login_required
    @manager_required
    def add_size():

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if not ensure_system_ready():
            if is_ajax:
                return jsonify(success=False, message="النظام قيد الاسترجاع حالياً"), 503
            return redirect(url_for("dashboard"))

        if request.method == "POST":

            result = validate_size_name(request.form.get("name", ""))

            if not result.valid:
                if is_ajax:
                    return jsonify(success=False, message=result.message), 400
                flash(result.message, "danger")
                return redirect(url_for("add_size"))

            name = result.data

            exists = Size.query.filter_by(name=name).first()
            if exists:
                if is_ajax:
                    return jsonify(success=False, message="هذا الحجم موجود مسبقاً"), 409
                flash("هذا الحجم موجود مسبقاً", "warning")
                return redirect(url_for("add_size"))

            size = Size(name=name)

            try:
                db.session.add(size)
                db.session.commit()

                log_activity(
                    current_user.id,
                    "ADD_SIZE",
                    f"اضافة الحجم: {size.name}"
                )

                if is_ajax:
                    return jsonify(success=True, id=size.id, name=size.name)

                flash("تمت إضافة الحجم بنجاح", "success")

            except IntegrityError:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="هذا الحجم موجود مسبقاً"), 409
                flash("هذا الحجم موجود مسبقاً (DB)", "warning")

            except Exception:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="حدث خطأ أثناء الحفظ"), 500
                flash("حدث خطأ أثناء الحفظ", "danger")

            return redirect(url_for("add_size"))

        sizes = Size.query.order_by(Size.id.desc()).all()
        return render_template("add_size.html", sizes=sizes)


    # =========================
    # EDIT (MODAL POST ONLY)
    # =========================
    @app.route("/size/<int:size_id>/edit", methods=["POST"])
    @login_required
    @admin_required
    def edit_size(size_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))
        size = Size.query.get_or_404(size_id)

        result = validate_size_name(request.form.get("name", ""))

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("add_size"))

        name = result.data

        exists = Size.query.filter(
            Size.name == name,
            Size.id != size.id
        ).first()

        if exists:
            flash("هذا الحجم موجود مسبقاً", "warning")
            return redirect(url_for("add_size"))

        size.name = name
        db.session.commit()

        flash("تم تعديل الحجم بنجاح", "success")
        log_activity(
            current_user.id,
            "EDIT_SIZE",
            f"تعديل الحجم: {size.name}"
        )
        return redirect(url_for("add_size"))


    # =========================
    # DELETE
    # =========================
    @app.route("/size/<int:size_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_size(size_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        size = Size.query.get_or_404(size_id)

        in_use = Product.query.filter_by(size_id=size.id).first() is not None

        if in_use:
            flash("لا يمكن حذف حجم مستخدم في منتجات", "danger")
            return redirect(url_for("add_size"))

        name = size.name

        db.session.delete(size)
        db.session.commit()

        log_activity(
            current_user.id,
            "DELETE_SIZE",
            f"حذف الحجم: {name}"
        )

        flash("تم حذف الحجم بنجاح", "success")
        return redirect(url_for("add_size"))
