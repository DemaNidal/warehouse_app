from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app
)

from flask_login import login_required, current_user

from models import (
    db,
    Product,
    Warehouse,
    InventoryLocation,
    InventoryTransaction
)

from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.location import validate_location


def register_location_routes(app):

    # =========================
    # ADD LOCATION
    # =========================
    @app.route("/product/<int:product_id>/add-location", methods=["GET", "POST"])
    @login_required
    @manager_required
    def add_location(product_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)

        if request.method == "POST":

            result = validate_location(request.form)

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("add_location", product_id=product.id))

            data = result.data
            warehouse = Warehouse.query.get(data["warehouse_id"])
            resolved_location_name = data["location"] or (warehouse.name if warehouse else "")

            # safety: prevent duplicates (DB-level safety still recommended)
            exists = InventoryLocation.query.filter_by(
                product_id=product.id,
                warehouse_id=data["warehouse_id"],
                location=resolved_location_name
            ).first()

            if exists:
                flash("هذا الموقع موجود مسبقاً", "warning")
                return redirect(url_for("add_location", product_id=product.id))

            location = InventoryLocation(
                product_id=product.id,
                warehouse_id=data["warehouse_id"],
                quantity=data["quantity"],
                location=resolved_location_name
            )

            db.session.add(location)
            db.session.commit()

            if location.quantity > 0:
                db.session.add(InventoryTransaction(
                    product_id=product.id,
                    location_id=location.id,
                    transaction_type="IN",
                    quantity=location.quantity,
                    notes=f"إضافة موقع جديد: {location.location or 'بدون موقع'}",
                    user_id=current_user.id
                ))
                db.session.commit()

            log_activity(
                current_user.id,
                "ADD_LOCATION",
                f"إضافة الموقع {location.location or 'بدون موقع'} للمنتج {product.name}"
            )

            flash("تمت إضافة الموقع بنجاح", "success")

            return redirect(url_for("product_details", product_id=product.id))

        warehouses = Warehouse.query.order_by(Warehouse.name).all()

        return render_template(
            "add_location.html",
            product=product,
            warehouses=warehouses
        )

    # =========================
    # EDIT LOCATION
    # =========================
    @app.route("/location/<int:location_id>/edit", methods=["GET", "POST"])
    @login_required
    @manager_required
    def edit_location(location_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        location = InventoryLocation.query.get_or_404(location_id)

        if request.method == "POST":

            name = request.form.get("location", "").strip()
            if not name:
                name = location.warehouse.name if location.warehouse else ""

            if len(name) > 255:
                flash("اسم الموقع طويل جداً", "danger")
                return redirect(url_for("edit_location", location_id=location.id))

            # prevent duplicates
            exists = InventoryLocation.query.filter(
                InventoryLocation.product_id == location.product_id,
                InventoryLocation.warehouse_id == location.warehouse_id,
                InventoryLocation.location == name,
                InventoryLocation.id != location.id
            ).first()

            if exists:
                flash("هذا الموقع موجود مسبقاً", "warning")
                return redirect(url_for("edit_location", location_id=location.id))

            old_name = location.location
            location.location = name

            db.session.commit()

            log_activity(
                current_user.id,
                "EDIT_LOCATION",
                f"تعديل الموقع '{old_name}' → '{name}'"
            )

            flash("تم تعديل الموقع بنجاح", "success")

            return redirect(
                url_for("product_details", product_id=location.product_id)
            )

        return render_template(
            "edit_location.html",
            location=location
        )

    # =========================
    # DELETE LOCATION
    # =========================
    @app.route("/location/<int:location_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_location(location_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        location = InventoryLocation.query.get_or_404(location_id)
        product_id = location.product_id

        if location.quantity > 0:
            flash("لا يمكن حذف موقع يحتوي على كمية", "danger")
            return redirect(url_for("product_details", product_id=product_id))

        has_history = InventoryTransaction.query.filter(
            db.or_(
                InventoryTransaction.location_id == location.id,
                InventoryTransaction.destination_location_id == location.id
            )
        ).first() is not None

        if has_history:
            flash("لا يمكن حذف هذا الموقع لوجود سجل حركات مرتبط به", "danger")
            return redirect(url_for("product_details", product_id=product_id))

        location_name = location.location

        try:
            db.session.delete(location)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Delete location #%s failed", location_id)
            flash("تعذر حذف الموقع بسبب بيانات مرتبطة به", "danger")
            return redirect(url_for("product_details", product_id=product_id))

        log_activity(
            current_user.id,
            "DELETE_LOCATION",
            f"حذف الموقع {location_name}"
        )

        flash("تم حذف الموقع بنجاح", "success")

        return redirect(url_for("product_details", product_id=product_id))