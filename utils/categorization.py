"""Keyword-based product categorisation.

One source of truth for two jobs:
  * back-filling the 91 products that were entered before categories existed
  * suggesting a category while someone types a new product name

Rules are ordered and the FIRST match wins, so the specific keywords sit above
the generic ones ("علب زجاج" must reach زجاج before جارات وعلب picks up "علب").
"""

import re


# ---------------------------------------------------------------- normalising

def normalize(text):
    """Same shape as normalize_color_name, plus neck-size punctuation.

    Products were entered by hand over months, so "28\\410" and "28/410" and
    "أبيض"/"ابيض" all have to collapse onto one spelling before matching.
    """
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"[\\/]", "/", text)
    text = re.sub(r"\s+", " ", text)

    return text.lower()


# ---------------------------------------------------------------- definitions

# (name, slug, icon, sort_order) — seeded on first run, editable afterwards
DEFAULT_CATEGORIES = [
    ("بمبات وبخاخات", "pumps", "bi-moisture", 1),
    ("أغطية", "caps", "bi-disc", 2),
    ("جارات وعلب", "jars", "bi-box", 3),
    ("زجاج", "glass", "bi-cup-straw", 4),
    ("تيوبات وايرلس", "tubes", "bi-eyedropper", 5),
    ("بريفورم وسدادات", "preforms", "bi-capsule", 6),
    ("عبوات غذائية", "food", "bi-basket", 7),
    ("جلنات", "gallons", "bi-bucket", 8),
    ("كبسولات", "capsules", "bi-capsule-pill", 9),
]

# (category, keywords, exclusions) — first rule whose keyword matches and whose
# exclusions do NOT wins. Order is load-bearing:
#   * food first, or "علب خل مائدة الشنار" gets swallowed by the generic jar rule
#   * pumps before caps, so "بمب سبريه مع غطاء" stays a pump
#   * glass before jars, so "علب زجاج مطبوع" lands in زجاج
CATEGORY_RULES = [
    (
        "عبوات غذائية",
        ["خل", "ليمون", "لبنه", "فرش اب", "هاي فرش", "عسل", "مائده"],
        [],
    ),
    (
        "بمبات وبخاخات",
        ["بمب", "بخاخ", "pump", "سبريه", "سبراي", "ترايجر"],
        [],
    ),
    (
        "تيوبات وايرلس",
        ["تيوب", "ايرلس", "airless"],
        [],
    ),
    (
        "بريفورم وسدادات",
        ["بريفورم", "preform", "سداده", "سداد"],
        [],
    ),
    (
        # before أغطية on purpose: that rule matches "كبس" (for "كبسة"), and
        # "كبس" is the start of "كبسولة" — a capsule would be filed as a cap
        "كبسولات",
        ["كبسول", "capsule"],
        [],
    ),
    (
        "أغطية",
        ["غطاء", "غطا", "كبس"],
        # "جار زجاج مطبوع مع غطاء فضي" is a jar that ships with a cap,
        # not a cap. The container it names comes first.
        ["مع غطاء"],
    ),
    (
        # after أغطية on purpose: "غطاء جلن" is a cap for a gallon, and the
        # cap rule has to claim it first
        "جلنات",
        ["جلن", "جالون", "غالون"],
        [],
    ),
    (
        "زجاج",
        ["زجاج"],
        # "للزجاج" means *used for* glass, not *made of* glass — a metal cap
        # for glass bottles is a cap. Both spellings are listed because the
        # catalogue has "للزجاح" with a ح, and the item is an accessory
        # either way.
        # "ملمع زجاج" is likewise a bottle for glass polish, not glass
        # packaging — it falls through to جارات وعلب below.
        ["للزجاج", "للزجاح", "ملمع"],
    ),
    (
        "جارات وعلب",
        ["جار", "مرطبان", "علب", "علبه", "فانتوم", "بدين", "قبه", "ملمع"],
        [],
    ),
]


def suggest_category_name(product_name):
    """Return the category name for a product name, or None if nothing matches."""

    haystack = normalize(product_name)

    if not haystack:
        return None

    for category_name, keywords, exclusions in CATEGORY_RULES:

        if any(normalize(bad) in haystack for bad in exclusions):
            continue

        for keyword in keywords:
            if normalize(keyword) in haystack:
                return category_name

    return None


def suggest_category(product_name, categories):
    """Same, but resolved against real Category rows.

    `categories` is any iterable of Category objects; matching is done on the
    normalised name so a renamed category still resolves.
    """

    name = suggest_category_name(product_name)

    if not name:
        return None

    target = normalize(name)

    for category in categories:
        if normalize(category.name) == target:
            return category

    return None
