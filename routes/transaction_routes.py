from datetime import datetime

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    abort,
    flash
)

from models import (
    TRANSACTION_LABELS,
    db,
    Product,
    InventoryLocation,
    InventoryTransaction,
    TRANSACTION_TYPES
)
from flask_login import login_required, current_user
from utils.notifications import generate_stock_notifications
from models import User

from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.transaction import validate_transaction


def register_transaction_routes(app):

    @app.route(
        "/product/<int:product_id>/transaction/add",
        methods=["GET", "POST"]
    )
    @login_required
    @manager_required
    def add_transaction(product_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)

        if request.method == "POST":

            result = validate_transaction(request.form)

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("add_transaction", product_id=product.id))

            data = result.data

            transaction_type = data["transaction_type"]
            quantity = data["quantity"]
            notes = data["notes"]

            try:
                location = InventoryLocation.query.filter_by(
                    id=data["location_id"],
                    product_id=product.id
                ).first_or_404()

                if transaction_type == "OUT" and location.quantity < quantity:
                    flash("الكمية المطلوبة أكبر من المتوفر", "danger")
                    return redirect(url_for("add_transaction", product_id=product.id))

                transaction = InventoryTransaction(
                    product_id=product.id,
                    location_id=location.id,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    notes=notes,
                    user_id=current_user.id
                )

                if transaction_type == "IN":
                    location.quantity += quantity

                elif transaction_type == "OUT":
                    location.quantity -= quantity

                elif transaction_type == "ADJUSTMENT":
                    location.quantity = quantity

                db.session.add(transaction)

                db.session.commit()

                # notifications AFTER commit (safe side-effect)
                try:
                    users = User.query.all()
                    generate_stock_notifications(product, users)
                except Exception:
                    pass  # don't break transaction if notifications fail

                log_activity(
                    current_user.id,
                    "STOCK_TRANSACTION",
                    f"{transaction_type} | Product: {product.name} | "
                    f"Location: {location.location} | Qty: {quantity}"
                )

                return redirect(url_for("product_details", product_id=product.id))

            except Exception:
                db.session.rollback()
                flash("حدث خطأ أثناء تسجيل الحركة", "danger")
                return redirect(url_for("add_transaction", product_id=product.id))