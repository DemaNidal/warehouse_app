# -*- coding: utf-8 -*-
"""Listing the catalogue.

One card per product. Grouping products into families is a real thing in the
data — see utils/families — but the catalogue page deliberately does not
collapse them: a warehouse list is read looking for one specific colour, and a
collapsed card hides exactly what is being looked for. Families have their own
pages instead.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from models import InventoryLocation, Product

PER_PAGE = 20

SORTS = ("recent", "oldest", "name", "quantity")


def _location_totals():
    return (
        select(
            InventoryLocation.product_id.label("product_id"),
            func.sum(InventoryLocation.quantity).label("total_qty"),
        )
        .group_by(InventoryLocation.product_id)
        .subquery()
    )


def browse_flat(category_filter="", stock_filter="", sort="recent", page=1,
                per_page=PER_PAGE):
    """The same page with every product on its own card.

    Grouping is a view, not a change to the data, so it has to be possible to
    turn off — when someone is looking for one specific colour, a collapsed
    card is in the way.
    """

    totals = _location_totals()
    qty = func.coalesce(totals.c.total_qty, 0)

    query = (
        Product.query
        .options(
            joinedload(Product.color),
            joinedload(Product.secondary_color),
            joinedload(Product.size_data),
            joinedload(Product.neck_size),
            joinedload(Product.category),
            joinedload(Product.family),
            joinedload(Product.locations),
        )
        .outerjoin(totals, totals.c.product_id == Product.id)
    )

    if category_filter == "none":
        query = query.filter(Product.category_id.is_(None))
    elif category_filter:
        try:
            query = query.filter(Product.category_id == int(category_filter))
        except (TypeError, ValueError):
            category_filter = ""

    if stock_filter == "critical":
        query = query.filter(qty == 0)
    elif stock_filter == "low":
        query = query.filter(qty > 0, qty <= Product.minimum_stock)
    elif stock_filter == "normal":
        query = query.filter(qty > Product.minimum_stock)
    else:
        stock_filter = ""

    if sort == "oldest":
        query = query.order_by(Product.id.asc())
    elif sort == "name":
        query = query.order_by(Product.name.asc())
    elif sort == "quantity":
        query = query.order_by(qty.desc(), Product.id.desc())
    else:
        sort = "recent"
        query = query.order_by(Product.id.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    units = [
        {
            "kind": "product",
            "family": None,
            "product": product,
            "quantity": product.total_quantity,
            "status": product.stock_status,
        }
        for product in pagination.items
    ]

    return pagination, units, category_filter, stock_filter, sort
