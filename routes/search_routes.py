from flask import render_template, request
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload,aliased
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
        warehouse_id = request.args.get("warehouse_id", type=int)
        page = request.args.get("page", 1, type=int)
        per_page = 20

        warehouses = Warehouse.query.order_by(Warehouse.name).all()

        # alias مهم لتجنب ambiguity
        inv = aliased(InventoryLocation)

        query = Product.query.options(
            joinedload(Product.color),
            joinedload(Product.size_data),
            joinedload(Product.locations)
        )

        # join آمن للمخزون
        query = query.outerjoin(inv, inv.product_id == Product.id)

        # فلتر warehouse (إذا موجود)
        if warehouse_id:
            query = query.filter(inv.warehouse_id == warehouse_id)

        # search
        if q:
            query = query.join(Color).join(Size).filter(
                or_(
                    Product.name.ilike(f"%{q}%"),
                    Color.name.ilike(f"%{q}%"),
                    Size.name.ilike(f"%{q}%"),
                    inv.location.ilike(f"%{q}%")   # 👈 هذا اللي رجّع "رف 1"
                )
            )

        query = query.distinct()

        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

        return render_template(
            "search.html",
            products=pagination.items,
            pagination=pagination,
            q=q,
            warehouses=warehouses,
            selected_warehouse=warehouse_id,
            total_count=pagination.total
        )