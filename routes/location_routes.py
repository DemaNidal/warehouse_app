from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from flask_login import login_required, current_user

from models import (
    db,
    Product,
    Warehouse,
    InventoryLocation
)

from utils.activity_logger import log_activity
from utils.permissions import manager_required
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

            # safety: prevent duplicates (DB-level safety still recommended)
            exists = InventoryLocation.query.filter_by(
                product_id=product.id,
                warehouse_id=data["warehouse_id"],
                location=data["location"]
            ).first()

            if exists:
                flash("هذا الموقع موجود مسبقاً", "warning")
                return redirect(url_for("add_location", product_id=product.id))

            location = InventoryLocation(
                product_id=product.id,
                warehouse_id=data["warehouse_id"],
                quantity=data["quantity"],
                location=data["location"]
            )

            db.session.add(location)
            db.session.commit()

            log_activity(
                current_user.id,
                "ADD_LOCATION",
                f"Added location {location.location} for {product.name}"
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
                flash("الموقع مطلوب", "danger")
                return redirect(url_for("edit_location", location_id=location.id))

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
                f"Changed location '{old_name}' → '{name}'"
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
    @manager_required
    def delete_location(location_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        location = InventoryLocation.query.get_or_404(location_id)
        product_id = location.product_id

        if location.quantity > 0:
            flash("لا يمكن حذف موقع يحتوي على كمية", "danger")
            return redirect(url_for("product_details", product_id=product_id))

        db.session.delete(location)
        db.session.commit()

        log_activity(
            current_user.id,
            "DELETE_LOCATION",
            f"Deleted location {location.location}"
        )

        flash("تم حذف الموقع بنجاح", "success")

        return redirect(url_for("product_details", product_id=product_id))