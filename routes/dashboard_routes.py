from flask import render_template

from models import (
    Product,
    Warehouse,
    InventoryLocation,
    Color
)
from flask_login import login_required

def register_dashboard_routes(app):

    @app.route("/dashboard")
    @login_required
    def dashboard():

        total_quantity = sum(
            location.quantity
            for location in InventoryLocation.query.all()
        )

        return render_template(
            "dashboard.html",
            product_count=Product.query.count(),
            color_count=Color.query.count(),
            warehouse_count=Warehouse.query.count(),
            location_count=InventoryLocation.query.count(),
            total_quantity=total_quantity
        )