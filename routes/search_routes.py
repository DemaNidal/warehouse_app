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

from utils.categorization import normalize
from utils.search_text import tokenize_query
from utils.shelves import parse_shelf, location_matches, strip_shelf

PER_PAGE = 24


def register_search_routes(app):

    @app.route("/search")
    @login_required
    def search():
        """Search and filter the catalogue.

        Text matching runs against Product.search_text — one normalised column
        per product covering its name, colours, category and measurements —
        and, live, against the shelf locations the product is stocked on. That
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
        # A shelf reference in the query ("رف 199 خانة 2") is read as a
        # structure — shelf number plus slots — and matched against the
        # locations the same way. Word by word it goes wrong: the digit "2"
        # matches a 250 مل bottle on that shelf as readily as slot 2 does.
        # Whatever is left of the query after the reference is taken out is
        # searched normally.
        shelf = parse_shelf(q)
        remaining = q

        if shelf is not None:
            # narrow in SQL to this shelf's rows, then decide in Python where
            # the slot logic lives — the rows for one shelf are a handful
            folded_shelf = func.lower(
                func.translate(InventoryLocation.location, "إأآىة\\", "ااايه/")
            )
            candidates = (
                db.session.query(InventoryLocation.product_id, InventoryLocation.location)
                .filter(folded_shelf.ilike(f"%رف {shelf['shelf']}%"))
                .all()
            )
            on_shelf = {
                product_id for product_id, location in candidates
                if location_matches(location, shelf)
            }
            query = query.filter(Product.id.in_(on_shelf) if on_shelf else db.false())
            remaining = strip_shelf(q, shelf)

        # every remaining word must appear, so extra words narrow the result
        # instead of widening it — which is what someone typing a second word
        # expects. A word may also match free-text on a location ("اصانصيل"),
        # read live so it is never stale.
        folded_location = func.lower(
            func.translate(InventoryLocation.location, "إأآىة\\", "ااايه/")
        )

        word_conditions = []
        for token in tokenize_query(remaining):
            on_a_matching_location = (
                db.session.query(InventoryLocation.product_id)
                .filter(folded_location.ilike(f"%{token}%"))
                .subquery()
            )
            word_conditions.append(
                db.or_(
                    Product.search_text.ilike(f"%{token}%"),
                    Product.id.in_(db.select(on_a_matching_location)),
                )
            )

        if word_conditions:
            matches_words = db.and_(*word_conditions)

            # A query that IS a category name ("أغطية", "زجاج") also means
            # that category, so its products come too — alongside, not
            # instead of, the products whose own words match: "زجاج" should
            # still find "ملمع زجاج" even though that is filed under jars.
            # Matched by the whole name on purpose: as a substring, "جار"
            # would drag in everything under "جارات وعلب".
            wanted = normalize(remaining)
            named_category = next(
                (c for c in Category.query.all() if normalize(c.name) == wanted),
                None,
            )
            if named_category is not None:
                matches_words = db.or_(
                    matches_words, Product.category_id == named_category.id
                )

            query = query.filter(matches_words)

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
