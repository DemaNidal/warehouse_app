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
from routes.backup_routes import RESTORE_IN_PROGRESS
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required


def register_transfer_routes(app):

    @app.route(
        "/product/<int:product_id>/transfer",
        methods=["GET", "POST"]
    )
    @login_required
    @manager_required
    def transfer_stock(product_id):
        if RESTORE_IN_PROGRESS:
            flash("System is restoring backup. Try again later.", "warning")
            return redirect(url_for("dashboard"))
        product = Product.query.get_or_404(
            product_id
        )

        locations = (
            InventoryLocation.query
            .filter_by(product_id=product.id)
            .all()
        )

        if request.method == "POST":

            source_id = int(
                request.form["source_location_id"]
            )

            destination_id = int(
                request.form["destination_location_id"]
            )

            try:
                quantity = int(request.form["quantity"])
            except ValueError:
                flash("الكمية غير صحيحة", "danger")
                return redirect(
                    url_for(
                        "transfer_stock",
                        product_id=product.id
                    )
                )

            notes = request.form.get(
                "notes",
                ""
            )

            if quantity <= 0:

                flash(
                    "الكمية يجب أن تكون أكبر من صفر",
                    "danger"
                )

                return redirect(
                    url_for(
                        "transfer_stock",
                        product_id=product.id
                    )
                )

            if source_id == destination_id:

                flash(
                    "لا يمكن التحويل إلى نفس الموقع",
                    "danger"
                )

                return redirect(
                    url_for(
                        "transfer_stock",
                        product_id=product.id
                    )
                )

            source_location = (
                InventoryLocation.query
                .get_or_404(source_id)
            )

            destination_location = (
                InventoryLocation.query
                .get_or_404(destination_id)
            )

            if (
                source_location.product_id
                != product.id
                or
                destination_location.product_id
                != product.id
            ):

                flash(
                    "بيانات التحويل غير صحيحة",
                    "danger"
                )

                return redirect(
                    url_for(
                        "transfer_stock",
                        product_id=product.id
                    )
                )

            if source_location.quantity < quantity:

                flash(
                    "الكمية المطلوبة أكبر من المتوفر",
                    "danger"
                )

                return redirect(
                    url_for(
                        "transfer_stock",
                        product_id=product.id
                    )
                )

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

            product.updated_at = datetime.utcnow()

            db.session.add(transaction)

            db.session.commit()
            log_activity(
                current_user.id,
                "STOCK_TRANSFER",
                (
                    f"TRANSFER | "
                    f"{product.name} | "
                    f"{source_location.location} -> "
                    f"{destination_location.location} | "
                    f"Qty={quantity}"
                )
            )

            flash(
                "تم التحويل بنجاح",
                "success"
            )

            return redirect(
                url_for(
                    "product_details",
                    product_id=product.id
                )
            )

        return render_template(
            "transfer_stock.html",
            product=product,
            locations=locations
        )