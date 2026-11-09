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
from utils.search_text import refresh_search_text_for
from utils.color_names import suggest_hex
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

            submitted_hex = request.form.get("hex_code", "").strip()

            # The quick-add modal on the product form sends a name and
            # nothing else, so a colour added from there was stored with no
            # code and drew as the same grey as every colour missing one.
            # Only if the suggestion is free, though: the validator refuses a
            # code another colour already carries, and a suggestion nobody
            # asked for must not become the reason a colour is rejected.
            if not submitted_hex:
                suggested = suggest_hex(request.form.get("name", ""))

                if suggested and not Color.query.filter(
                    Color.hex_code.ilike(suggested)
                ).first():
                    submitted_hex = suggested

            result = validate_color_name(
                request.form.get("name", ""),
                submitted_hex
            )

            if not result.valid:
                if is_ajax:
                    return jsonify(success=False, message=result.message), 400
                flash(result.message, "danger")
                return redirect(url_for("add_color"))

            data = result.data

            color = Color(name=data["name"], hex_code=data["hex_code"])

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

        usage_counts = {}
        for row in db.session.query(Product.color_id, db.func.count(Product.id)).group_by(Product.color_id):
            if row[0] is not None:
                usage_counts[row[0]] = usage_counts.get(row[0], 0) + row[1]
        for row in db.session.query(Product.secondary_color_id, db.func.count(Product.id)).group_by(Product.secondary_color_id):
            if row[0] is not None:
                usage_counts[row[0]] = usage_counts.get(row[0], 0) + row[1]

        return render_template("add_color.html", colors=colors, usage_counts=usage_counts)


    # =========================
    # SUGGEST A HEX (AJAX, used by the add-colour form)
    # =========================
    @app.route("/colors/suggest-hex")
    @login_required
    @manager_required
    def suggest_color_hex():
        """What colour an Arabic colour name means.

        Server-side on purpose, the same as the category suggestion: the
        names live in one module, so the form, the quick-add and anything
        else that needs them cannot drift apart.
        """

        return jsonify(success=True, hex_code=suggest_hex(request.args.get("name", "")))


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

        result = validate_color_name(
            request.form.get("name", ""),
            request.form.get("hex_code", ""),
            exclude_id=color.id
        )

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("add_color"))

        data = result.data

        color.name = data["name"]
        color.hex_code = data["hex_code"]

        # The name is copied into the search_text of every product using
        # this colour, so a rename that stops at this row leaves the
        # catalogue findable only under the spelling nobody will type
        # again.
        refresh_search_text_for(
            Product.query.filter(
                db.or_(
                    Product.color_id == color.id,
                    Product.secondary_color_id == color.id
                )
            ).all()
        )

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

        in_use = Product.query.filter(
            db.or_(
                Product.color_id == color.id,
                Product.secondary_color_id == color.id
            )
        ).first() is not None

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


