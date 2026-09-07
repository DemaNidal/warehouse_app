"""One normalised blob of text per product, so search can be both correct and fast.

Two problems that look separate are really the same one. Searching "اسود" used
to miss "أسود" because the hamza differs, and `ILIKE '%…%'` across five joined
tables cannot use an index at all. Folding every searchable word for a product
into a single normalised column solves both: the spelling is settled before
storage, and one trigram index covers the lot.

What goes in: the product name, its family name, both colours, the category,
the capacity and the neck size — everything a person might type when they are
looking for it.
"""

from utils.categorization import normalize


def build_search_text(product):
    """Everything worth matching on, normalised and space-separated."""

    parts = [product.name]

    if product.family:
        # a family can be renamed to the term buyers actually use; without it
        # here, that name would find nothing
        parts.append(product.family.name)

    if product.color:
        parts.append(product.color.name)

    if product.secondary_color:
        parts.append(product.secondary_color.name)

    if product.category:
        parts.append(product.category.name)

    if product.size_data:
        parts.append(product.size_data.name)

    if product.neck_size:
        # people search "رقبة 28/410" as often as the bare number
        parts.append(product.neck_size.name)
        parts.append(f"رقبة {product.neck_size.name}")

    normalised = [normalize(part) for part in parts if part]

    # de-duplicate while keeping order, so a colour that repeats the name
    # ("جار زجاج" + "زجاج") does not bloat the column
    seen = set()
    words = []
    for chunk in normalised:
        for word in chunk.split():
            if word not in seen:
                seen.add(word)
                words.append(word)

    return " ".join(words)


def refresh_search_text(product):
    """Recompute and assign. Call after any change to a product's fields.

    Also refreshes normalized_name, which is the same folding applied to the
    name alone — grouping looks products up by it, and letting the two drift
    apart would mean a renamed product quietly stops matching its siblings.
    """
    product.search_text = build_search_text(product)
    product.normalized_name = normalize(product.name)
    return product.search_text


def tokenize_query(raw):
    """Split what the user typed into normalised words.

    Every word must match, which is what makes "غطاء ازرق" work — those two
    words live in different columns on the original tables.
    """
    if not raw:
        return []
    return [word for word in normalize(raw).split() if word]
