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
    Notification,
    StockRequest,
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

            location = InventoryLocation.query.filter_by(
                id=data["location_id"],
                product_id=product.id
            ).first_or_404()

            transaction_type = data["transaction_type"]
            quantity = data["quantity"]
            notes = data.get("notes", "")

            try:

                # =========================
                # IN → مباشر
                # =========================
                if transaction_type == "IN":

                    location.quantity += quantity

                    transaction = InventoryTransaction(
                        product_id=product.id,
                        location_id=location.id,
                        transaction_type="IN",
                        quantity=quantity,
                        notes=notes,
                        user_id=current_user.id
                    )

                    db.session.add(transaction)
                    db.session.commit()

                # =========================
                # OUT → طلب موافقة
                # =========================
                elif transaction_type == "OUT":

                    if location.quantity < quantity:
                        flash("الكمية غير كافية", "danger")
                        return redirect(url_for("add_transaction", product_id=product.id))

                    stock_request = StockRequest(
                        product_id=product.id,
                        location_id=location.id,
                        quantity=quantity,
                        notes=notes,
                        requested_by=current_user.id,
                        status="PENDING"
                    )

                    db.session.add(stock_request)

                    # 🔔 NOTIFY ADMINS
                    admin_users = User.query.filter_by(role="ADMIN").all()

                    for admin in admin_users:
                        db.session.add(Notification(
                            user_id=admin.id,
                            product_id=product.id,
                            type="OUT_REQUEST",
                            is_read=False
                        ))

                    db.session.commit()

                    flash("تم إرسال طلب إخراج للموافقة", "success")
                    return redirect(url_for("product_details", product_id=product.id))

                # =========================
                # ADJUSTMENT → مباشر
                # =========================
                elif transaction_type == "ADJUSTMENT":

                    location.quantity = quantity

                    transaction = InventoryTransaction(
                        product_id=product.id,
                        location_id=location.id,
                        transaction_type="ADJUSTMENT",
                        quantity=quantity,
                        notes=notes,
                        user_id=current_user.id
                    )

                    db.session.add(transaction)
                    db.session.commit()

                flash("تم تسجيل العملية بنجاح", "success")

                return redirect(url_for("product_details", product_id=product.id))

            except Exception:
                db.session.rollback()
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
    @app.route("/product/<int:product_id>/request-out", methods=["POST"])
    @login_required
    @manager_required
    def request_out(product_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)

        location_id = request.form.get("location_id")
        quantity = int(request.form.get("quantity"))
        notes = request.form.get("notes", "")

        location = InventoryLocation.query.filter_by(
            id=location_id,
            product_id=product.id
        ).first_or_404()

        if location.quantity < quantity:
            flash("الكمية غير كافية", "danger")
            return redirect(url_for("product_details", product_id=product.id))

        req = StockRequest(
            product_id=product.id,
            location_id=location.id,
            quantity=quantity,
            notes=notes,
            requested_by=current_user.id,
            status="PENDING"
        )

        db.session.add(req)
        db.session.commit()

        flash("تم إرسال طلب الموافقة", "success")

        return redirect(url_for("product_details", product_id=product.id))
    
    @app.route("/stock-requests")
    @login_required
    @admin_required
    def stock_requests():

        requests = StockRequest.query.order_by(
            StockRequest.created_at.desc()
        ).all()

        return render_template(
            "stock_requests.html",
            requests=requests
        )
    
    @app.route("/stock-request/<int:request_id>/approve", methods=["POST"])
    @login_required
    @admin_required
    def approve_request(request_id):

        req = StockRequest.query.get_or_404(request_id)

        if req.status != "PENDING":
            abort(400)

        location = InventoryLocation.query.get_or_404(req.location_id)

        if location.quantity < req.quantity:
            flash("الكمية لم تعد متوفرة", "danger")
            return redirect(url_for("stock_requests"))

        # خصم المخزون
        location.quantity -= req.quantity

        # تسجيل حركة
        transaction = InventoryTransaction(
            product_id=req.product_id,
            location_id=req.location_id,
            transaction_type="OUT",
            quantity=req.quantity,
            notes=req.notes,
            user_id=req.requested_by
        )

        req.status = "APPROVED"
        req.approved_by = current_user.id

        db.session.add(transaction)

        # 🔔 notify requester
        db.session.add(Notification(
            user_id=req.requested_by,
            product_id=req.product_id,
            type="OUT_APPROVED",
            is_read=False
        ))

        db.session.commit()

        flash("تمت الموافقة على الطلب", "success")
        return redirect(url_for("stock_requests"))
    

    @app.route("/stock-request/<int:request_id>/reject", methods=["POST"])
    @login_required
    @admin_required
    def reject_request(request_id):

        req = StockRequest.query.get_or_404(request_id)

        if req.status != "PENDING":
            abort(400)

        req.status = "REJECTED"
        req.approved_by = current_user.id

        db.session.commit()

        flash("تم رفض الطلب", "warning")

        return redirect(url_for("stock_requests"))