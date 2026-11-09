# -*- coding: utf-8 -*-
"""Arabic colour names, and the hex each one means.

This lived in base.html as a JavaScript object, next to a second hand-written
copy of the Arabic normaliser that utils/validation/color.py already had. Two
copies of the same knowledge in two languages is the thing utils/text_search.py
refuses to do, for the reason it gives there: the first time one of them is
fixed, the other is wrong and nobody notices.

**Matching takes the LAST name it recognises, not the first.** Arabic puts the
qualifier after the base colour — "اخضر زيتي" is olive, "ازرق سماوي" is sky
blue, "احمر عنابي" is maroon — so the word that narrows the colour is the
second one. The rule this replaces walked the list in definition order and
returned on the first hit, which meant it answered with the broad colour every
single time: six of twelve ordinary names came back wrong, and olive green was
suggested as #16A34A, a bright grass green.

**Whole words only.** The old rule asked whether the key appeared anywhere in
the text, so "لبني" — which contains "بني" — was suggested as brown. A name
nothing matches now produces no suggestion, which leaves the colour picker
wherever the person left it. A suggestion that is silently wrong is worse than
no suggestion, because this one writes itself into the field.
"""

from utils.categorization import normalize


# The grey that means "this colour has no code recorded". One value, because
# the templates had each picked their own — #e2e8f0, #94A3B8, #ccc and
# #cccccc — so the same state drew differently depending on the page.
EMPTY_SWATCH = "#E2E8F0"


# Keys are already in normalised spelling (ا, ي, ه), so a name typed with any
# of the variants folds onto them.
COLOR_NAME_HEX = {
    "ابيض": "#F8FAFC",
    "احمر": "#DC2626",
    "اخضر": "#16A34A",
    "ازرق": "#2563EB",
    "اسود": "#111827",
    "اصفر": "#FACC15",
    "برتقالي": "#F97316",
    "بني": "#92400E",
    "ثلجي": "#DBEAFE",
    "ذهبي": "#D4AF37",
    "زهري": "#EC4899",
    "وردي": "#EC4899",
    "سكني": "#9CA3AF",
    "رمادي": "#9CA3AF",
    "شفاف": "#E5E7EB",
    "فضي": "#C0C0C0",
    "فوشي": "#D946EF",
    "كحلي": "#1E293B",
    "بحري": "#1E3A5F",
    "بنفسجي": "#7C3AED",
    "خزامي": "#C4B5FD",
    "موف": "#B784A7",
    "تركواز": "#14B8A6",
    "فيروزي": "#14B8A6",
    "زيتي": "#6B7C3A",
    "كريمي": "#F5E6C8",
    "بيج": "#E8DCC4",
    "عنابي": "#7C1F2E",
    "خمري": "#7C1F2E",
    "نحاسي": "#B87333",
    "برونزي": "#CD7F32",
    "سماوي": "#38BDF8",
    "نيلي": "#4338CA",
    "ليموني": "#D9E021",
    "قرمزي": "#DC143C",
}


def suggest_hex(name):
    """The hex a colour name means, or None when nothing is recognised.

    The last recognised word wins — see the module docstring for why.
    """

    for word in reversed(normalize(name).split()):
        if word in COLOR_NAME_HEX:
            return COLOR_NAME_HEX[word]

    return None


def swatch(hex_code):
    """A colour's hex, or the one grey that means it has none."""

    return (hex_code or "").strip() or EMPTY_SWATCH
