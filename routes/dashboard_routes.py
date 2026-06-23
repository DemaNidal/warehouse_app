from flask import render_template
from flask_login import login_required, current_user

from models import (
    Product,
    InventoryTransaction,
    Notification,
    STOCK_LOW,
    STOCK_CRITICAL
)


def register_dashboard_routes(app):

    @app.route("/dashboard")
    @login_required
    def dashboard():

        # ⚠️ consider replacing with filtered query later
        products = Product.query.all()

        low_stock_products = [
            p for p in products
            if p.stock_status in (STOCK_LOW, STOCK_CRITICAL)
        ]

        # sort: critical first, then lowest stock
        low_stock_products.sort(
            key=lambda p: (
                p.stock_status != STOCK_CRITICAL,
                p.total_quantity
            )
        )

        attention_count = len(low_stock_products)

        critical_count = sum(
            1 for p in low_stock_products
            if p.stock_status == STOCK_CRITICAL
        )

        unread_notifications = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()

        recent_transactions = (
            InventoryTransaction.query
            .order_by(InventoryTransaction.created_at.desc())
            .limit(8)
            .all()
        )

        return render_template(
            "dashboard.html",
            product_count=len(products),
            attention_count=attention_count,
            critical_count=critical_count,
            unread_notifications=unread_notifications,
            low_stock_products=low_stock_products,
            recent_transactions=recent_transactions,
            STOCK_LOW=STOCK_LOW,
            STOCK_CRITICAL=STOCK_CRITICAL
        )