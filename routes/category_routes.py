from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

from models import db, Category, Product
from flask_login import current_user, login_required
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.category import validate_category_name
from utils.categorization import suggest_category
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload


def register_category_routes(app):

    # =========================
    # ADD + LIST
    # =========================
    @app.route("/add-category", methods=["GET", "POST"])
    @login_required
    @manager_required
    def add_category():

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if not ensure_system_ready():
            if is_ajax:
                return jsonify(success=False, message="النظام قيد الاسترجاع حالياً"), 503
            return redirect(url_for("dashboard"))

        if request.method == "POST":

            result = validate_category_name(
                request.form.get("name", ""),
                request.form.get("icon", "")
            )

            if not result.valid:
                if is_ajax:
                    return jsonify(success=False, message=result.message), 400
                flash(result.message, "danger")
                return redirect(url_for("add_category"))

            data = result.data

            next_order = (
                db.session.query(db.func.coalesce(db.func.max(Category.sort_order), 0)).scalar()
                + 1
            )

            category = Category(
                name=data["name"],
                icon=data["icon"],
                sort_order=next_order
            )

            try:
                db.session.add(category)
                db.session.commit()

                log_activity(
                    current_user.id,
                    "ADD_CATEGORY",
                    f"اضافة التصنيف: {category.name}"
                )

                if is_ajax:
                    return jsonify(success=True, id=category.id, name=category.name)

                flash("تمت إضافة التصنيف بنجاح", "success")

            except IntegrityError:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="هذا التصنيف موجود مسبقاً"), 409
                flash("هذا التصنيف موجود مسبقاً (DB)", "warning")

            except Exception:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="حدث خطأ أثناء الحفظ"), 500
                flash("حدث خطأ أثناء الحفظ", "danger")

            return redirect(url_for("add_category"))

        categories = (
            Category.query
            .options(joinedload(Category.products))
            .order_by(Category.sort_order, Category.id)
            .all()
        )

        uncategorized_count = Product.query.filter(
            Product.category_id.is_(None)
        ).count()

        return render_template(
            "add_category.html",
            categories=categories,
            uncategorized_count=uncategorized_count
        )


    # =========================
    # EDIT (MODAL)
    # =========================
    @app.route("/category/<int:category_id>/edit", methods=["POST"])
    @login_required
    @admin_required
    def edit_category(category_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        category = Category.query.get_or_404(category_id)

        result = validate_category_name(
            request.form.get("name", ""),
            request.form.get("icon", ""),
            exclude_id=category.id
        )

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("add_category"))

        data = result.data

        category.name = data["name"]
        category.icon = data["icon"]

        db.session.commit()

        log_activity(
            current_user.id,
            "EDIT_CATEGORY",
            f"تعديل التصنيف: {category.name}"
        )

        flash("تم تعديل التصنيف بنجاح", "success")
        return redirect(url_for("add_category"))


    # =========================
    # DELETE
    # =========================
    @app.route("/category/<int:category_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_category(category_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        category = Category.query.get_or_404(category_id)

        in_use = Product.query.filter_by(category_id=category.id).first() is not None

        if in_use:
            flash("لا يمكن حذف تصنيف مستخدم في منتجات", "danger")
            return redirect(url_for("add_category"))

        name = category.name

        db.session.delete(category)
        db.session.commit()

        log_activity(
            current_user.id,
            "DELETE_CATEGORY",
            f"حذف التصنيف: {name}"
        )

        flash("تم حذف التصنيف بنجاح", "success")
        return redirect(url_for("add_category"))


    # =========================
    # SUGGEST (AJAX, used by the add/edit product forms)
    # =========================
    @app.route("/categories/suggest")
    @login_required
    @manager_required
    def suggest_product_category():
        """Guess a category from a half-typed product name.

        Kept server-side on purpose: the keyword rules live in one module, so
        the form and the back-fill script can never drift apart.
        """

        name = request.args.get("name", "")

        if not name.strip():
            return jsonify(success=True, id=None, name=None)

        categories = Category.query.all()
        match = suggest_category(name, categories)

        if not match:
            return jsonify(success=True, id=None, name=None)

        return jsonify(success=True, id=match.id, name=match.name)
