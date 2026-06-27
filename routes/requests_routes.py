from flask import (
    render_template,
    redirect,
    request,
    url_for,
    abort,
    flash
)

from flask_login import login_required, current_user

from models import (
    db,
    User,
    StockRequest,
    Notification,
    InventoryLocation,
    InventoryTransaction,
    Product
)

from utils.activity_logger import log_activity
from utils.notifications import generate_stock_notifications
from utils.permissions import admin_required


def register_requests_routes(app):

    # =========================================================
    # STOCK REQUESTS LIST (FILTERED + ODOO STYLE READY)
    # =========================================================
    @app.route("/stock-requests")
    @login_required
    @admin_required
    def stock_requests():

        # BASE QUERY
        base_query = StockRequest.query

        # FILTERS
        status = request.args.get("status")
        product_id = request.args.get("product")
        user_id = request.args.get("user")

        if product_id:
            base_query = base_query.filter(StockRequest.product_id == int(product_id))

        if user_id:
            base_query = base_query.filter(StockRequest.requested_by == int(user_id))

        # IMPORTANT: split queries for tabs
        pending_requests = base_query.filter(StockRequest.status == "PENDING") \
            .order_by(StockRequest.created_at.desc()).all()

        approved_requests = base_query.filter(StockRequest.status == "APPROVED") \
            .order_by(StockRequest.created_at.desc()).all()

        rejected_requests = base_query.filter(StockRequest.status == "REJECTED") \
            .order_by(StockRequest.created_at.desc()).all()

        all_requests = base_query.order_by(StockRequest.created_at.desc()).all()

        # dropdowns
        products = Product.query.all()
        users = User.query.all()

        return render_template(
            "stock_requests.html",
            pending_requests=pending_requests,
            approved_requests=approved_requests,
            rejected_requests=rejected_requests,
            all_requests=all_requests,
            products=products,
            users=users,
            active_status=status or "all",
            selected_product=product_id,
            selected_user=user_id
        )

    # =========================================================
    # APPROVE REQUEST
    # =========================================================
    @app.route("/stock-request/<int:request_id>/approve", methods=["POST"])
    @login_required
    @admin_required
    def approve_request(request_id):

        req = StockRequest.query.get_or_404(request_id)

        if req.status != "PENDING":
            flash("Request already processed", "warning")
            return redirect(url_for("stock_requests"))

        location = InventoryLocation.query.get_or_404(req.location_id)

        if location.quantity < req.quantity:
            flash("Not enough stock available", "danger")
            return redirect(url_for("stock_requests"))

        try:
            # reduce stock
            location.quantity -= req.quantity

            # log transaction
            db.session.add(InventoryTransaction(
                product_id=req.product_id,
                location_id=req.location_id,
                transaction_type="OUT",
                quantity=req.quantity,
                notes=req.notes,
                user_id=req.requested_by
            ))

            # update request
            req.status = "APPROVED"
            req.approved_by = current_user.id
            req.approved_at = db.func.now()

            db.session.add(req)
            db.session.commit()

            # notifications
            generate_stock_notifications(req.product, User.query.all())

            log_activity(
                current_user.id,
                "APPROVE_STOCK_REQUEST",
                f"Request #{req.id}"
            )

            flash("Request approved successfully", "success")

        except Exception as e:
            db.session.rollback()
            flash("Approval failed", "danger")

        return redirect(url_for("stock_requests"))

    # =========================================================
    # REJECT REQUEST
    # =========================================================
    @app.route("/stock-request/<int:request_id>/reject", methods=["POST"])
    @login_required
    @admin_required
    def reject_request(request_id):

        req = StockRequest.query.get_or_404(request_id)

        if req.status != "PENDING":
            flash("Request already processed", "warning")
            return redirect(url_for("stock_requests"))

        try:

            req.status = "REJECTED"
            req.approved_by = current_user.id
            req.rejected_at = db.func.now()

            db.session.add(req)

            db.session.add(Notification(
                user_id=req.requested_by,
                product_id=req.product_id,
                type="OUT_REJECTED",
                is_read=False,
                target_url=url_for("product_details", product_id=req.product_id)
            ))

            db.session.commit()

            flash("Request rejected", "warning")

        except Exception:
            db.session.rollback()
            flash("Reject failed", "danger")

        return redirect(url_for("stock_requests"))
    

    