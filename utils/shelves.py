# -*- coding: utf-8 -*-
"""Reading shelf references the way the warehouse writes them.

Locations follow one pattern by convention:

    رف 199               the whole shelf
    رف 199 خانة 2        one slot on it
    رف 199 خانة 1-2-3    one pile spread over several slots

Matching these word by word goes wrong in a way that is hard to see: the
digit "2" on its own matches a 250 مل bottle on shelf 199 just as well as slot
2 does, so "رف 199 خانة 2" brings back products that are not in slot 2. The
fix is to stop treating a shelf reference as loose words and read it as what it
is — a shelf number and, optionally, a set of slots — on both sides of the
comparison.

Dash-separated slots are a list, not a range: "1-3" is slots 1 and 3. The
convention writes every slot out ("1-2-3"), so there is nothing to expand.
"""

import re

from utils.categorization import normalize

# "رف 199" with an optional "خانة 1-2-3" after it. The slot part accepts
# digits joined by dashes, commas or "و", and spaces around them.
_SHELF = re.compile(
    r"رف\s*(?P<shelf>\d+)"
    r"(?:\s*خانه\s*(?P<slots>\d+(?:\s*[-,،و]\s*\d+)*))?"
)

_SLOT_SPLIT = re.compile(r"\s*[-,،و]\s*")


def parse_shelf(text):
    """The shelf reference in `text`, or None if there is none.

    Returns a dict with `shelf` (str), `slots` (set of str, empty when the
    reference names the whole shelf) and `span` (the matched substring), so a
    caller can take the reference out of a query and search the rest normally.
    """

    folded = normalize(text)
    match = _SHELF.search(folded)
    if not match:
        return None

    slots = set()
    if match.group("slots"):
        slots = {s for s in _SLOT_SPLIT.split(match.group("slots")) if s}

    return {
        "shelf": match.group("shelf"),
        "slots": slots,
        "span": match.group(0),
    }


def location_matches(location_text, wanted):
    """Does a stored location satisfy a parsed shelf reference?

    Same shelf number, always. Then: asking for the whole shelf matches every
    location on it; asking for particular slots matches only a location that
    names at least one of them — a location that names no slot at all is the
    shelf itself, not the slot, and does not count.
    """

    have = parse_shelf(location_text or "")
    if have is None or have["shelf"] != wanted["shelf"]:
        return False

    if not wanted["slots"]:
        return True

    return bool(have["slots"] & wanted["slots"])


def strip_shelf(query, parsed):
    """The query with the shelf reference removed, for the ordinary search."""

    folded = normalize(query)
    return folded.replace(parsed["span"], " ", 1).strip()
