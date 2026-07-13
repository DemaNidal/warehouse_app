from flask import render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import (
    db,
    Product,
    InventoryLocation,
    InventoryTransaction,
    Notification,
    STOCK_LOW,
    STOCK_CRITICAL,
    StockRequest,
    TRANSACTION_LABELS
)
from utils.permissions import manager_required


def register_dashboard_routes(app):

    @app.route("/dashboard")
    @login_required
    @manager_required
    def dashboard():

        product_count = Product.query.count()

        # total quantity per product, computed in SQL instead of loading
        # every Product + its locations into Python
        location_totals = (
            db.session.query(
                InventoryLocation.product_id.label("product_id"),
                func.sum(InventoryLocation.quantity).label("total_qty")
            )
            .group_by(InventoryLocation.product_id)
            .subquery()
        )

        total_qty = func.coalesce(location_totals.c.total_qty, 0)

        # low/critical stock = total quantity <= minimum_stock (matches
        # Product.stock_status: qty == 0 is CRITICAL, qty <= minimum_stock is LOW)
        # ordering by qty ascending naturally puts all qty == 0 (critical)
        # products first, then the rest of the low-stock products by qty
        low_stock_products = (
            Product.query
            .options(joinedload(Product.locations))
            .outerjoin(
                location_totals,
                location_totals.c.product_id == Product.id
            )
            .filter(total_qty <= Product.minimum_stock)
            .order_by(total_qty.asc())
            .all()
        )

        attention_count = len(low_stock_products)

        critical_count = sum(
            1 for p in low_stock_products
            if p.stock_status == STOCK_CRITICAL
        )

        pending_requests_count = StockRequest.query.filter_by(status="PENDING").count()

        unread_notifications = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()

        recent_transactions = (
            InventoryTransaction.query
            .options(
                joinedload(InventoryTransaction.product),
                joinedload(InventoryTransaction.user)
            )
            .order_by(InventoryTransaction.created_at.desc())
            .limit(8)
            .all()
        )

        return render_template(
            "dashboard.html",
            product_count=product_count,
            attention_count=attention_count,
            critical_count=critical_count,
            unread_notifications=unread_notifications,
            low_stock_products=low_stock_products,
            recent_transactions=recent_transactions,
            transaction_labels=TRANSACTION_LABELS,
            STOCK_LOW=STOCK_LOW,
            STOCK_CRITICAL=STOCK_CRITICAL
        )