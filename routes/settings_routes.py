from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from flask_login import login_required, current_user

from models import db, Warehouse
from utils.permissions import admin_required
from utils.activity_logger import log_activity
from utils.system_guard import ensure_system_ready
from utils.validation.warehouse import validate_warehouse_name
from sqlalchemy.exc import IntegrityError


def register_settings_routes(app):

    # =========================
    # SETTINGS HUB
    # =========================
    @app.route("/settings")
    @login_required
    @admin_required
    def settings_page():

        warehouses = Warehouse.query.order_by(Warehouse.name).all()

        return render_template(
            "settings.html",
            warehouses=warehouses
        )

    # =========================
    # ADD WAREHOUSE
    # =========================
    @app.route("/settings/warehouse/add", methods=["POST"])
    @login_required
    @admin_required
    def add_warehouse():

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        result = validate_warehouse_name(request.form.get("name", ""))

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("settings_page"))

        name = result.data

        exists = Warehouse.query.filter_by(name=name).first()

        if exists:
            flash("هذا المستودع موجود مسبقاً", "warning")
            return redirect(url_for("settings_page"))

        warehouse = Warehouse(name=name)

        try:
            db.session.add(warehouse)
            db.session.commit()

            log_activity(
                current_user.id,
                "ADD_WAREHOUSE",
                f"اضافة المستودع: {warehouse.name}"
            )

            flash("تمت إضافة المستودع بنجاح", "success")

        except IntegrityError:
            db.session.rollback()
            flash("هذا المستودع موجود مسبقاً (DB)", "warning")

        except Exception:
            db.session.rollback()
            flash("حدث خطأ أثناء الحفظ", "danger")

        return redirect(url_for("settings_page"))

    # =========================
    # EDIT WAREHOUSE
    # =========================
    @app.route("/settings/warehouse/<int:warehouse_id>/edit", methods=["POST"])
    @login_required
    @admin_required
    def edit_warehouse(warehouse_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        warehouse = Warehouse.query.get_or_404(warehouse_id)

        result = validate_warehouse_name(request.form.get("name", ""))

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("settings_page"))

        name = result.data

        exists = Warehouse.query.filter(
            Warehouse.name == name,
            Warehouse.id != warehouse.id
        ).first()

        if exists:
            flash("هذا المستودع موجود مسبقاً", "warning")
            return redirect(url_for("settings_page"))

        old_name = warehouse.name
        warehouse.name = name

        db.session.commit()

        log_activity(
            current_user.id,
            "EDIT_WAREHOUSE",
            f"تعديل المستودع '{old_name}' → '{name}'"
        )

        flash("تم تعديل المستودع بنجاح", "success")

        return redirect(url_for("settings_page"))

    # =========================
    # DELETE WAREHOUSE
    # =========================
    @app.route("/settings/warehouse/<int:warehouse_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_warehouse(warehouse_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        warehouse = Warehouse.query.get_or_404(warehouse_id)

        if warehouse.locations:
            flash("لا يمكن حذف مستودع يحتوي على مواقع مرتبطة به", "danger")
            return redirect(url_for("settings_page"))

        name = warehouse.name

        db.session.delete(warehouse)
        db.session.commit()

        log_activity(
            current_user.id,
            "DELETE_WAREHOUSE",
            f"حذف المستودع: {name}"
        )

        flash("تم حذف المستودع بنجاح", "success")

        return redirect(url_for("settings_page"))
