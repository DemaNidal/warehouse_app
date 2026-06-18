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

from routes.backup_routes import RESTORE_IN_PROGRESS
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required


def register_transaction_routes(app):

    @app.route(
        "/product/<int:product_id>/transaction/add",
        methods=["GET", "POST"]
    )
    @login_required
    @manager_required
    def add_transaction(product_id):
        if RESTORE_IN_PROGRESS:
            flash("System is restoring backup. Try again later.", "warning")
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(
            product_id
        )

        if request.method == "POST":

            transaction_type = request.form[
                "transaction_type"
            ]

            if transaction_type not in TRANSACTION_TYPES:
                abort(400)

            location = InventoryLocation.query.get_or_404(
                request.form["location_id"]
            )

            if location.product_id != product.id:
                abort(400)

            quantity = int(
                request.form["quantity"]
            )

            if quantity <= 0:
                abort(400)

            notes = request.form.get(
                "notes",
                ""
            )

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

                if location.quantity < quantity:

                    flash(
                        "الكمية المطلوبة أكبر من المتوفر في الموقع",
                        "danger"
                    )

                    return redirect(
                        url_for(
                            "add_transaction",
                            product_id=product.id
                        )
                    )

                location.quantity -= quantity

            elif transaction_type == "ADJUSTMENT":

                location.quantity = quantity


            product.updated_at = datetime.utcnow()

            db.session.add(
                transaction
            )

            db.session.commit()

            log_activity(
                current_user.id,
                "STOCK_TRANSACTION",
                (
                    f"{transaction_type} | "
                    f"Product: {product.name} | "
                    f"Location: {location.location} | "
                    f"Qty: {quantity}"
                )
            )

            return redirect(
                url_for(
                    "product_details",
                    product_id=product.id
                )
            )

        locations = InventoryLocation.query.filter_by(
            product_id=product.id
        ).all()

        return render_template(
            "add_transaction.html",
            product=product,
            locations=locations,
            transaction_types=TRANSACTION_TYPES,
            transaction_labels=TRANSACTION_LABELS

        )