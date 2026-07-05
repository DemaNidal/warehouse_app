import datetime

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
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta

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

        # ----------------------------------
        # Filters
        # ----------------------------------

        q = request.args.get("q", "").strip()

        status = request.args.get(
            "status",
            ""
        ).strip()

        product_id = request.args.get(
            "product",
            type=int
        )

        user_id = request.args.get(
            "user",
            type=int
        )

        date = request.args.get(
            "date",
            ""
        )

        # ----------------------------------
        # Sorting
        # ----------------------------------

        sort = request.args.get(
            "sort",
            "created_at"
        )

        direction = request.args.get(
            "direction",
            "desc"
        )

        # ----------------------------------
        # Pagination
        # ----------------------------------

        page = request.args.get(
            "page",
            1,
            type=int
        )

        per_page = 20

        # ----------------------------------
        # Base Query
        # ----------------------------------

        query = (
            StockRequest.query
            .options(
                joinedload(StockRequest.product),
                joinedload(StockRequest.location),
                joinedload(StockRequest.requester),
                joinedload(StockRequest.approver)
            )
            .join(Product)
        )

        # ----------------------------------
        # Search
        # ----------------------------------

        if q:
            query = query.filter(
                Product.name.ilike(f"%{q}%")
            )

        # ----------------------------------
        # Filters
        # ----------------------------------

        if status:
            query = query.filter(
                StockRequest.status == status
            )

        if product_id:
            query = query.filter(
                StockRequest.product_id == product_id
            )

        if user_id:
            query = query.filter(
                StockRequest.requested_by == user_id
            )

        if date:
            selected_date = datetime.strptime(date, "%Y-%m-%d")

            next_day = selected_date + timedelta(days=1)

            query = query.filter(
                StockRequest.created_at >= selected_date,
                StockRequest.created_at < next_day
            )

        # ----------------------------------
        # Sorting
        # ----------------------------------

        sortable_columns = {
            "created_at": StockRequest.created_at,
            "quantity": StockRequest.quantity,
            "status": StockRequest.status,
            "product": Product.name
        }

        column = sortable_columns.get(
            sort,
            StockRequest.created_at
        )

        if direction == "asc":
            query = query.order_by(column.asc())
        else:
            query = query.order_by(column.desc())

        # ----------------------------------
        # Pagination
        # ----------------------------------

        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

        requests = pagination.items

        # ----------------------------------
        # Summary Cards
        # ----------------------------------

        pending_count = db.session.query(func.count(StockRequest.id)).filter(
            StockRequest.status == "PENDING"
        ).scalar()

        approved_count = db.session.query(func.count(StockRequest.id)).filter(
            StockRequest.status == "APPROVED"
        ).scalar()

        rejected_count = db.session.query(func.count(StockRequest.id)).filter(
            StockRequest.status == "REJECTED"
        ).scalar()

        total_count = db.session.query(
            func.count(StockRequest.id)
        ).scalar()

        # ----------------------------------
        # Dropdowns
        # ----------------------------------

        products = Product.query.order_by(
            Product.name
        ).all()

        users = User.query.order_by(
            User.username
        ).all()

        return render_template(
            "stock_requests.html",

            requests=requests,
            pagination=pagination,

            pending_count=pending_count,
            approved_count=approved_count,
            rejected_count=rejected_count,
            total_count=total_count,

            products=products,
            users=users,

            q=q,
            status=status,
            product_id=product_id,
            user_id=user_id,
            date=date,

            sort=sort,
            direction=direction
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
    

    