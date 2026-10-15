# -*- coding: utf-8 -*-
"""Matching what someone typed against the catalogue.

This used to live inside the /search route. The products page needed the same
thing — the same tolerance for spelling, the same reading of "رف 199 خانة 2" —
and a second copy would have drifted the first time one of them was fixed. So
it sits here, and both callers narrow their query through it.
"""

from sqlalchemy import func

from models import Category, InventoryLocation, Product, db
from utils.categorization import normalize
from utils.search_text import tokenize_query
from utils.shelves import location_matches, parse_shelf, strip_shelf


def _folded(column):
    """The column with Arabic spelling variants flattened, in SQL.

    Done in the database rather than in Python because the shelf text is read
    live — it is never denormalised into search_text, so it cannot be folded
    in advance the way a product's own words are.
    """
    return func.lower(func.translate(column, "إأآىة\\", "ااايه/"))


def apply_text_search(query, raw):
    """Narrow `query` (a Product query) to what `raw` asks for.

    A shelf reference is read as a structure — shelf number plus slots — and
    matched against the locations the same way. Word by word it goes wrong:
    the digit "2" matches a 250 مل bottle on that shelf as readily as slot 2
    does. Whatever is left of the query after the reference is taken out is
    searched normally.
    """
    raw = (raw or "").strip()
    if not raw:
        return query

    shelf = parse_shelf(raw)
    remaining = raw

    if shelf is not None:
        # narrow in SQL to this shelf's rows, then decide in Python where the
        # slot logic lives — the rows for one shelf are a handful
        candidates = (
            db.session.query(
                InventoryLocation.product_id, InventoryLocation.location
            )
            .filter(_folded(InventoryLocation.location).ilike(f"%رف {shelf['shelf']}%"))
            .all()
        )
        on_shelf = {
            product_id for product_id, location in candidates
            if location_matches(location, shelf)
        }
        query = query.filter(
            Product.id.in_(on_shelf) if on_shelf else db.false()
        )
        remaining = strip_shelf(raw, shelf)

    # every remaining word must appear, so extra words narrow the result
    # instead of widening it — which is what someone typing a second word
    # expects. A word may also match free text on a location ("اصانصيل"),
    # read live so it is never stale.
    word_conditions = []
    for token in tokenize_query(remaining):
        on_a_matching_location = (
            db.session.query(InventoryLocation.product_id)
            .filter(_folded(InventoryLocation.location).ilike(f"%{token}%"))
            .subquery()
        )
        word_conditions.append(
            db.or_(
                Product.search_text.ilike(f"%{token}%"),
                Product.id.in_(db.select(on_a_matching_location)),
            )
        )

    if not word_conditions:
        return query

    matches_words = db.and_(*word_conditions)

    # A query that IS a category name ("أغطية", "زجاج") also means that
    # category, so its products come too — alongside, not instead of, the
    # products whose own words match: "زجاج" should still find "ملمع زجاج"
    # even though that is filed under jars. Matched by the whole name on
    # purpose: as a substring, "جار" would drag in everything under
    # "جارات وعلب".
    wanted = normalize(remaining)
    named_category = next(
        (c for c in Category.query.all() if normalize(c.name) == wanted),
        None,
    )
    if named_category is not None:
        matches_words = db.or_(
            matches_words, Product.category_id == named_category.id
        )

    return query.filter(matches_words)
