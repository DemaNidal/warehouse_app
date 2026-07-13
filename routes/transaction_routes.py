from flask import (
    render_template,
    request,
    redirect,
    url_for,
    abort,
    flash,
    current_app
)

from flask_login import login_required, current_user

from models import (
    db,
    Product,
    User,
    StockRequest,
    Notification,
    InventoryLocation,
    InventoryTransaction,
    TRANSACTION_TYPES,
    TRANSACTION_LABELS
)

from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.transaction import validate_transaction
from utils.notifications import generate_stock_notifications
from utils.activity_logger import log_activity
from sqlalchemy.orm import joinedload


def register_transaction_routes(app):

    # =========================================================
    # ADD TRANSACTION
    # =========================================================
    @app.route("/product/<int:product_id>/transaction/add", methods=["GET", "POST"])
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

            location = InventoryLocation.query.filter_by(
                id=data["location_id"],
                product_id=product.id
            ).first_or_404()

            transaction_type = data["transaction_type"]
            quantity = data["quantity"]
            notes = data.get("notes", "")

            try:

                # =====================================================
                # IN TRANSACTION
                # =====================================================
                if transaction_type == "IN":

                    qty_before = location.quantity
                    location.quantity += quantity

                    db.session.add(InventoryTransaction(
                        product_id=product.id,
                        location_id=location.id,
                        transaction_type="IN",
                        quantity=quantity,
                        quantity_before=qty_before,
                        quantity_after=location.quantity,
                        notes=notes,
                        user_id=current_user.id
                    ))

                # =====================================================
                # OUT TRANSACTION (REQUEST ONLY - NO NOTIFICATIONS)
                # =====================================================
                elif transaction_type == "OUT":

                    if location.quantity < quantity:
                        flash("الكمية غير كافية", "danger")
                        return redirect(url_for("add_transaction", product_id=product.id))

                    if current_user.role == "ADMIN":

                        qty_before = location.quantity
                        location.quantity -= quantity

                        db.session.add(InventoryTransaction(
                            product_id=product.id,
                            location_id=location.id,
                            transaction_type="OUT",
                            quantity=quantity,
                            quantity_before=qty_before,
                            quantity_after=location.quantity,
                            notes=notes,
                            user_id=current_user.id
                        ))

                    else:

                        existing_request = StockRequest.query.filter_by(
                            product_id=product.id,
                            location_id=location.id,
                            requested_by=current_user.id,
                            status="PENDING"
                        ).first()

                        if existing_request:
                            flash("يوجد طلب معلق مسبقاً لهذا المنتج", "warning")
                            return redirect(url_for("product_details", product_id=product.id))

                        db.session.add(StockRequest(
                            product_id=product.id,
                            location_id=location.id,
                            quantity=quantity,
                            notes=notes,
                            requested_by=current_user.id,
                            status="PENDING"
                        ))

                        db.session.commit()   # ✅ IMPORTANT HERE

                        flash("تم إرسال طلب إخراج للموافقة", "success")
                        return redirect(url_for("product_details", product_id=product.id))

                # =====================================================
                # ADJUSTMENT
                # =====================================================
                elif transaction_type == "ADJUSTMENT":

                    qty_before = location.quantity
                    location.quantity = quantity

                    db.session.add(InventoryTransaction(
                        product_id=product.id,
                        location_id=location.id,
                        transaction_type="ADJUSTMENT",
                        quantity=quantity,
                        quantity_before=qty_before,
                        quantity_after=location.quantity,
                        notes=notes,
                        user_id=current_user.id
                    ))

                db.session.commit()

                # 🔔 CENTRALIZED STOCK NOTIFICATIONS ONLY
                # Only ADMIN/STORE_MANAGER can act on stock levels (restock, approve requests)
                users = User.query.filter(User.role.in_(["ADMIN", "STORE_MANAGER"])).all()
                generate_stock_notifications(product, users)
                db.session.commit()

                flash("تم تسجيل العملية بنجاح", "success")
                return redirect(url_for("product_details", product_id=product.id))

            except Exception:
                db.session.rollback()
                current_app.logger.exception("Transaction failed for product %s", product.id)
                flash("حدث خطأ أثناء العملية", "danger")
                return redirect(url_for("add_transaction", product_id=product.id))

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

    # =========================================================
    # ALL STOCK MOVEMENTS (full history, paginated + filterable)
    # =========================================================
    @app.route("/transactions")
    @login_required
    @manager_required
    def transactions_log():

        page = request.args.get("page", 1, type=int)
        selected_type = request.args.get("type", "")

        query = InventoryTransaction.query.options(
            joinedload(InventoryTransaction.product),
            joinedload(InventoryTransaction.user),
            joinedload(InventoryTransaction.location)
            .joinedload(InventoryLocation.warehouse),
            joinedload(InventoryTransaction.destination_location)
            .joinedload(InventoryLocation.warehouse)
        )

        if selected_type in TRANSACTION_TYPES:
            query = query.filter_by(transaction_type=selected_type)

        transactions = query.order_by(
            InventoryTransaction.created_at.desc()
        ).paginate(page=page, per_page=30, error_out=False, max_per_page=100)

        return render_template(
            "transactions_log.html",
            transactions=transactions,
            transaction_types=TRANSACTION_TYPES,
            transaction_labels=TRANSACTION_LABELS,
            selected_type=selected_type
        )
