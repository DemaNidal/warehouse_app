# -*- coding: utf-8 -*-
"""Grouping products that are the same item in another colour or size.

The rule here is that the system may *suggest* a grouping but never apply one.
Two earlier attempts grouped products automatically from their names, and both
were thrown away for the same reason: the guess was sometimes wrong and there
was no way to correct it. "بمب PUMP" and "بمب PUMP غالي" read as the same
product and are not.

So suggestions are proposals on a screen, and a family exists only because
someone approved it.
"""

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import (
    db,
    Product,
    ProductFamily,
    FamilySuggestionDismissal,
)
from utils.categorization import normalize
from utils.search_text import refresh_search_text


# Only exact name matches are proposed. Fuzzier matching finds a few more
# groups and a lot more wrong ones, and reviewing a wrong suggestion costs more
# attention than missing a right one — the missed ones can still be linked by
# hand.
def suggest_families(limit=None):
    """Groups of ungrouped products that share a name.

    Returns a list of proposals, each carrying the products and a note of what
    actually differs between them, so the reviewer can see at a glance whether
    the grouping makes sense.
    """

    dismissed = {
        row.normalized_name
        for row in FamilySuggestionDismissal.query.all()
    }

    # ask the database which names repeat, then fetch only those products —
    # otherwise opening this screen reads the whole catalogue
    repeated = [
        row[0]
        for row in (
            db.session.query(Product.normalized_name)
            .filter(Product.family_id.is_(None))
            .group_by(Product.normalized_name)
            .having(func.count(Product.id) > 1)
            .all()
        )
        if row[0] and row[0] not in dismissed
    ]

    if not repeated:
        return []

    products = (
        Product.query
        .options(
            joinedload(Product.color),
            joinedload(Product.size_data),
            joinedload(Product.neck_size),
        )
        .filter(Product.family_id.is_(None))
        .filter(Product.normalized_name.in_(repeated))
        .order_by(Product.id)
        .all()
    )

    grouped = {}
    for product in products:
        grouped.setdefault(product.normalized_name, []).append(product)

    proposals = []
    for key, members in grouped.items():
        if len(members) < 2:
            continue
        proposals.append({
            "key": key,
            "name": members[0].name,
            "products": members,
            "differs": _describe_difference(members),
        })

    proposals.sort(key=lambda p: (-len(p["products"]), p["name"]))

    return proposals[:limit] if limit else proposals


def _describe_difference(products):
    """What separates these products from each other."""

    colors = {p.color_id for p in products}
    capacities = {p.size_id for p in products}
    necks = {p.neck_size_id for p in products}

    varies_size = len(capacities) > 1 or len(necks) > 1

    if len(colors) > 1 and varies_size:
        return "اللون والمقاس"
    if len(colors) > 1:
        return "اللون"
    if varies_size:
        return "المقاس"

    # identical on every axis we track — worth flagging rather than hiding,
    # because it usually means a duplicate entry rather than a variant
    return "لا شيء ظاهر"


def create_family(name, products, category_id=None):
    """Group these products under a new family."""

    if len(products) < 2:
        raise ValueError("المجموعة لازم تحتوي منتجين على الأقل")

    if category_id is None:
        # inherit the category the members already agree on, if they do
        categories = {p.category_id for p in products if p.category_id}
        if len(categories) == 1:
            category_id = categories.pop()

    family = ProductFamily(name=name.strip(), category_id=category_id)
    db.session.add(family)
    db.session.flush()

    for product in products:
        product.family = family
        refresh_search_text(product)

    return family


def link_product(product, family):
    """Move a single product into an existing family.

    Assigns the relationship rather than `family_id`, so `product.family` is
    correct immediately — refresh_search_text reads it in the same breath, and
    a stale value would index the wrong name.
    """

    product.family = family
    refresh_search_text(product)
    return family


def unlink_product(product):
    """Take a product out of its family.

    Empties the family rather than leaving a one-member group behind — a family
    of one is just a product with extra indirection.
    """

    family = product.family
    product.family = None
    refresh_search_text(product)

    if family is not None:
        db.session.flush()
        remaining = [v for v in family.variants if v.id != product.id]
        if len(remaining) < 2:
            for variant in remaining:
                variant.family = None
                refresh_search_text(variant)
            db.session.delete(family)

    return family


def dismiss_suggestion(key):
    """Remember that these products are not the same item.

    Without this the same rejected proposal comes back on every visit, and a
    screen that keeps asking a question already answered stops being read.
    """

    existing = FamilySuggestionDismissal.query.filter_by(
        normalized_name=key
    ).first()

    if existing is None:
        db.session.add(FamilySuggestionDismissal(normalized_name=key))

    return existing is None


def find_match(product):
    """A family or sibling this product probably belongs with, or None.

    Called when a product page is opened, to offer the grouping at the moment
    someone is already looking at the thing. That timing is the whole point: a
    grouping screen visited on purpose becomes a backlog nobody opens once the
    catalogue is in the thousands, and the catalogue drifts back to one card
    per colour.

    Returns a dict with either an existing `family` to join or the loose
    `siblings` a new family would be made from.
    """

    if product.family_id is not None:
        return None

    key = product.normalized_name or normalize(product.name)

    if FamilySuggestionDismissal.query.filter_by(normalized_name=key).first():
        return None

    others = (
        Product.query
        .options(joinedload(Product.color), joinedload(Product.family))
        .filter(Product.id != product.id)
        .filter(Product.normalized_name == key)
        .order_by(Product.id)
        .all()
    )

    if not others:
        return None

    # if any of them is already in a family, joining it beats making a second
    # family for the same product
    families = [other.family for other in others if other.family is not None]
    if families:
        family = families[0]
        return {
            "key": key,
            "family": family,
            "siblings": [o for o in others if o.family_id == family.id],
        }

    return {"key": key, "family": None, "siblings": others}


def rename_family(family, name):
    """Rename a family and reindex its variants.

    The name is copied into each variant's search_text, so leaving it stale
    would make the family findable by a name it no longer has.
    """

    name = (name or "").strip()

    if not name:
        raise ValueError("اسم المجموعة مطلوب")

    family.name = name

    for variant in family.variants:
        refresh_search_text(variant)

    return family
