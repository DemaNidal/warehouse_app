# -*- coding: utf-8 -*-
"""Listing the catalogue — one card per product."""

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from models import InventoryLocation, Product
from utils.text_search import apply_text_search

PER_PAGE = 20

SORTS = ("recent", "oldest", "name", "quantity", "quantity_asc")


def _location_totals():
    return (
        select(
            InventoryLocation.product_id.label("product_id"),
            func.sum(InventoryLocation.quantity).label("total_qty"),
        )
        .group_by(InventoryLocation.product_id)
        .subquery()
    )




def apply_sort(query, sort, qty):
    """Order a product query, and say which order was actually used.

    Shared with /search, which had drifted into calling the same order by a
    different name. Every branch ends with the id: without a tiebreaker, rows
    tied on the sort key come back in whatever order the database feels like,
    and paging through them can show one product twice and another not at all.
    """
    if sort == "oldest":
        return query.order_by(Product.id.asc()), sort

    if sort == "name":
        return query.order_by(Product.name.asc(), Product.id.desc()), sort

    if sort == "quantity":
        return query.order_by(qty.desc(), Product.id.desc()), sort

    if sort == "quantity_asc":
        # what is nearly gone, first. The empty shelves lead, which is the
        # order you want in front of you when writing an order.
        return query.order_by(qty.asc(), Product.id.desc()), sort

    return query.order_by(Product.id.desc()), "recent"


def _where(product):
    """The one shelf worth printing on a card, and how many others there are.

    A card used to show how MANY places a product sat in, which answers a
    question nobody asks. The shelf with the most stock on it is the one you
    would walk to, so that is the one named; the rest become "+2".
    """
    places = [
        location for location in product.locations
        if (location.location or "").strip()
    ]
    if not places:
        return {"shelf": "", "others": max(len(product.locations) - 1, 0)}

    places.sort(key=lambda location: (-(location.quantity or 0), location.id))
    return {
        "shelf": places[0].location.strip(),
        "others": len(product.locations) - 1,
    }


def browse_flat(category_filter="", stock_filter="", warehouse_filter="",
                sort="recent", page=1, per_page=PER_PAGE, q=""):
    """One page of products, searched, filtered and sorted."""

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
            joinedload(Product.locations),
        )
        .outerjoin(totals, totals.c.product_id == Product.id)
    )

    # the same matcher /search uses, so a word that finds a product there
    # finds it here too
    query = apply_text_search(query, q)

    if category_filter == "none":
        query = query.filter(Product.category_id.is_(None))
    elif category_filter:
        try:
            query = query.filter(Product.category_id == int(category_filter))
        except (TypeError, ValueError):
            category_filter = ""

    # A product belongs to a warehouse when it has a place in it, even an
    # empty one — "شو عندي بهاد المستودع" includes the shelf that ran out,
    # which is usually the row worth acting on.
    if warehouse_filter:
        try:
            stocked_here = (
                select(InventoryLocation.product_id)
                .where(InventoryLocation.warehouse_id == int(warehouse_filter))
                .subquery()
            )
            query = query.filter(Product.id.in_(select(stocked_here)))
        except (TypeError, ValueError):
            warehouse_filter = ""

    if stock_filter == "critical":
        query = query.filter(qty == 0)
    elif stock_filter == "low":
        query = query.filter(qty > 0, qty <= Product.minimum_stock)
    elif stock_filter == "normal":
        query = query.filter(qty > Product.minimum_stock)
    else:
        stock_filter = ""

    query, sort = apply_sort(query, sort, qty)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    units = [
        {
            "kind": "product",
            "product": product,
            "quantity": product.total_quantity,
            "status": product.stock_status,
            **_where(product),
        }
        for product in pagination.items
    ]

    return (pagination, units, category_filter, stock_filter,
            warehouse_filter, sort)
