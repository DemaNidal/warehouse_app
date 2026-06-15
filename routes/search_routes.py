from flask import render_template, request
from sqlalchemy import or_

from models import (
    Product,
    Color,
    Warehouse,
    InventoryLocation,
    Size
)
from flask_login import login_required


def register_search_routes(app):

    @app.route("/search")
    @login_required
    def search():

        q = request.args.get("q", "").strip()

        warehouse_id = request.args.get("warehouse_id", "")

        warehouses = Warehouse.query.order_by(Warehouse.name).all()

        query = (
            Product.query
            .join(Color)
            .join(Size)
            .outerjoin(InventoryLocation)
        )

        # filter by warehouse
        if warehouse_id:
            query = query.filter(
                InventoryLocation.warehouse_id == int(warehouse_id)
            )

        # search filters
        if q:
            query = query.filter(
                or_(
                    Product.name.ilike(f"%{q}%"),
                    Size.name.ilike(f"%{q}%"),
                    Color.name.ilike(f"%{q}%"),
                    InventoryLocation.location.ilike(f"%{q}%")
                )
            )

        products = query.distinct().all()

        return render_template(
            "search.html",
            products=products,
            q=q,
            warehouses=warehouses,
            selected_warehouse=warehouse_id
        )