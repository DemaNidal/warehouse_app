from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)
from models import (
    db,
    Product,
    Warehouse,
    InventoryLocation
)
from flask_login import current_user, login_required


from utils.activity_logger import log_activity
from utils.permissions import manager_required
from utils.system_guard import ensure_system_ready
from utils.system_guard import ensure_system_ready
from utils.validation.location import validate_location

def register_location_routes(app):

    @app.route("/product/<int:product_id>/add-location", methods=["GET", "POST"])
    @login_required
    @manager_required
    def add_location(product_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)

        if request.method == "POST":

            location_name = request.form.get("location", "").strip()

            # if not location_name:
            #     flash("اسم الموقع مطلوب", "danger")
            #     return redirect(url_for("add_location", product_id=product.id))

            location = InventoryLocation(
                product_id=product.id,
                warehouse_id=request.form["warehouse_id"],
                location=location_name,
                quantity=request.form["quantity"]
            )

            db.session.add(location)
            db.session.commit()

            log_activity(
                current_user.id,
                "ADD_LOCATION",
                f"Added location {location.location} for {product.name}"
            )

            return redirect(url_for("product_details", product_id=product.id))

        # ✅ THIS IS REQUIRED (GET request)
        warehouses = Warehouse.query.order_by(Warehouse.name).all()

        return render_template(
            "add_location.html",
            product=product,
            warehouses=warehouses
        )
    @app.route(
        "/location/<int:location_id>/edit",
        methods=["GET", "POST"]
    )
    @login_required
    @manager_required
    def edit_location(location_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        location = InventoryLocation.query.get_or_404(
            location_id
        )

        if request.method == "POST":

            location.location = request.form["location"]

            

            db.session.commit()

            log_activity(
                current_user.id,
                "EDIT_LOCATION",
                f"Edited location {location.location}"
            )

            return redirect(
                url_for(
                    "product_details",
                    product_id=location.product_id
                )
            )
        

        return render_template(
            "edit_location.html",
            location=location
        )
    
    @app.route(
    "/location/<int:location_id>/delete",
    methods=["POST"]
    )
    @login_required
    @manager_required
    def delete_location(location_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        location = InventoryLocation.query.get_or_404(
            location_id
        )

        product_id = location.product_id

        if location.quantity > 0:

            flash(
                "لا يمكن حذف موقع يحتوي على كمية",
                "danger"
            )

            return redirect(
                url_for(
                    "product_details",
                    product_id=product_id
                )
            )

        db.session.delete(location)

        db.session.commit()

        flash(
            "تم حذف الموقع بنجاح",
            "success"
        )
        log_activity(
            current_user.id,
            "DELETE_LOCATION",
            f"Deleted location {location.location}"
        )

        return redirect(
            url_for(
                "product_details",
                product_id=product_id
            )
        )