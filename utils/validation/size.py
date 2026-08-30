import re

from .base import success, fail
from models import SIZE_KINDS, SIZE_KIND_CAPACITY


def normalize_size_name(name):
    """Canonicalise a size before it is stored.

    Neck sizes were entered inconsistently over time — "28\\410" with a
    backslash alongside "24/410" with a forward slash — which silently splits
    what is really one measurement into two values and breaks any filter or
    fit-matching built on it. A size name never legitimately contains a
    backslash, so it always becomes a forward slash, and spaces around the
    separator are dropped ("28 / 410" -> "28/410").
    """

    name = name.strip()
    name = name.replace("\\", "/")
    name = re.sub(r"\s*/\s*", "/", name)
    name = re.sub(r"\s+", " ", name)

    return name


def validate_size_name(name, kind=None):

    name = normalize_size_name(name)

    if not name:
        return fail("القياس مطلوب")

    if len(name) > 50:
        return fail("اسم القياس طويل جداً")

    kind = (kind or "").strip() or SIZE_KIND_CAPACITY

    if kind not in SIZE_KINDS:
        return fail("نوع القياس غير صحيح")

    return success({"name": name, "kind": kind})
