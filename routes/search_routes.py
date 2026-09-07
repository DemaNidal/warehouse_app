from flask import render_template, request, url_for

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import (
    db,
    Product,
    Color,
    Category,
    Warehouse,
    InventoryLocation,
    Size,
    SIZE_KIND_CAPACITY,
    SIZE_KIND_NECK,
)

from flask_login import login_required

from utils.search_text import tokenize_query

PER_PAGE = 24


def register_search_routes(app):

    @app.route("/search")
    @login_required
    def search():
        """Search and filter the catalogue.

        Text matching runs against Product.search_text — one normalised column
        per product covering its name, colours, category and measurements. That
        is what makes "اسود" find "أسود", lets "غطاء ازرق" match two words that
        live in different tables, and keeps the query on a trigram index
        instead of scanning every row.
        """

        q = request.args.get("q", "").strip()
        page = request.args.get("page", 1, type=int)

        filters = {
            # warehouse_id was the old name for this — still honoured so a
            # bookmarked search doesn't quietly come back unfiltered
            "warehouse": request.args.get("warehouse", type=int)
            or request.args.get("warehouse_id", type=int),
            "category": request.args.get("category", type=int),
            "neck": request.args.get("neck", type=int),
            "capacity": request.args.get("capacity", type=int),
            "color": request.args.get("color", type=int),
            "stock": request.args.get("stock", ""),
        }
        if filters["stock"] not in ("critical", "low", "normal"):
            filters["stock"] = ""

        # per-product totals, computed in SQL so the stock filter and the
        # pagination both stay in the database
        location_totals = (
            db.session.query(
                InventoryLocation.product_id.label("product_id"),
                func.sum(InventoryLocation.quantity).label("total_qty"),
            )
            .group_by(InventoryLocation.product_id)
            .subquery()
        )
        total_qty = func.coalesce(location_totals.c.total_qty, 0)

        query = (
            Product.query
            .options(
                joinedload(Product.color),
                joinedload(Product.secondary_color),
                joinedload(Product.category),
                joinedload(Product.size_data),
                joinedload(Product.neck_size),
                joinedload(Product.locations),
            )
            .outerjoin(location_totals, location_totals.c.product_id == Product.id)
        )

        # ---- text ----
        # every word must appear, so extra words narrow the result instead of
        # widening it — which is what someone typing a second word expects
        for token in tokenize_query(q):
            query = query.filter(Product.search_text.ilike(f"%{token}%"))

        # ---- facets ----
        if filters["category"]:
            query = query.filter(Product.category_id == filters["category"])

        if filters["neck"]:
            query = query.filter(Product.neck_size_id == filters["neck"])

        if filters["capacity"]:
            query = query.filter(Product.size_id == filters["capacity"])

        if filters["color"]:
            query = query.filter(
                db.or_(
                    Product.color_id == filters["color"],
                    Product.secondary_color_id == filters["color"],
                )
            )

        if filters["warehouse"]:
            stocked_here = (
                db.session.query(InventoryLocation.product_id)
                .filter(InventoryLocation.warehouse_id == filters["warehouse"])
                .subquery()
            )
            query = query.filter(Product.id.in_(db.select(stocked_here)))

        if filters["stock"] == "critical":
            query = query.filter(total_qty == 0)
        elif filters["stock"] == "low":
            query = query.filter(total_qty > 0, total_qty <= Product.minimum_stock)
        elif filters["stock"] == "normal":
            query = query.filter(total_qty > Product.minimum_stock)

        sort = request.args.get("sort", "recent")
        if sort == "name":
            query = query.order_by(Product.name.asc())
        elif sort == "quantity":
            query = query.order_by(total_qty.desc())
        elif sort == "oldest":
            query = query.order_by(Product.id.asc())
        else:
            sort = "recent"
            query = query.order_by(Product.id.desc())

        def url_with(**over):
            """Current search URL with a few parameters changed.

            Every filter link has to preserve the other filters, otherwise
            clicking a colour throws away the category you already picked.
            Passing None removes a parameter, which is what the "×" on a chip
            does.
            """
            params = {
                "q": q,
                "sort": sort,
                "category": filters["category"],
                "neck": filters["neck"],
                "capacity": filters["capacity"],
                "color": filters["color"],
                "warehouse": filters["warehouse"],
                "stock": filters["stock"],
            }
            params.update(over)
            return url_for(
                "search",
                **{k: v for k, v in params.items() if v}
            )

        pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)

        return render_template(
            "search.html",
            products=pagination.items,
            pagination=pagination,
            q=q,
            sort=sort,
            url_with=url_with,
            filters=filters,
            active_count=sum(1 for v in filters.values() if v),
            categories=Category.query.order_by(Category.sort_order, Category.id).all(),
            neck_sizes=Size.query.filter_by(kind=SIZE_KIND_NECK).order_by(Size.name).all(),
            capacities=Size.query.filter_by(kind=SIZE_KIND_CAPACITY).order_by(Size.name).all(),
            colors=Color.query.order_by(Color.name).all(),
            warehouses=Warehouse.query.order_by(Warehouse.name).all(),
            total_count=pagination.total,
        )
