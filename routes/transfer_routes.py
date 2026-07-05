from datetime import datetime

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
    InventoryLocation,
    InventoryTransaction
)
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.transfer import validate_transfer


def register_transfer_routes(app):

    @app.route(
        "/product/<int:product_id>/transfer",
        methods=["GET", "POST"]
    )
    @login_required
    @manager_required
    def transfer_stock(product_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)

        locations = InventoryLocation.query.filter_by(
            product_id=product.id
        ).all()

        if request.method == "POST":

            result = validate_transfer(request.form)

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("transfer_stock", product_id=product.id))

            data = result.data

            source_id = data["source_location_id"]
            destination_id = data["destination_location_id"]
            quantity = data["quantity"]
            notes = data["notes"]

            if source_id == destination_id:
                flash("لا يمكن التحويل لنفس الموقع", "warning")
                return redirect(url_for("transfer_stock", product_id=product.id))

            try:
                source_location = InventoryLocation.query.filter_by(
                    id=source_id,
                    product_id=product.id
                ).first_or_404()

                destination_location = InventoryLocation.query.filter_by(
                    id=destination_id,
                    product_id=product.id
                ).first_or_404()

                if source_location.quantity < quantity:
                    flash("الكمية المطلوبة أكبر من المتوفر", "danger")
                    return redirect(url_for("transfer_stock", product_id=product.id))

                source_location.quantity -= quantity
                destination_location.quantity += quantity

                transaction = InventoryTransaction(
                    product_id=product.id,
                    location_id=source_location.id,
                    destination_location_id=destination_location.id,
                    transaction_type="TRANSFER",
                    quantity=quantity,
                    notes=notes,
                    user_id=current_user.id
                )

                db.session.add(transaction)
                db.session.commit()

                log_activity(
                    current_user.id,
                    "STOCK_TRANSFER",
                    f"{product.name} | {source_location.location} -> "
                    f"{destination_location.location} | الكمية={quantity}"
                )

                flash("تم التحويل بنجاح", "success")

                return redirect(url_for("product_details", product_id=product.id))

            except Exception:
                db.session.rollback()
                flash("حدث خطأ أثناء التحويل", "danger")
                return redirect(url_for("transfer_stock", product_id=product.id))

        return render_template(
            "transfer_stock.html",
            product=product,
            locations=locations
        )