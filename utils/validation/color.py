import re

from .base import success, fail
from models import Color

HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_color_name(name):
    text = name.strip()
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def validate_color_name(name, hex_code=None, exclude_id=None):

    name = name.strip()

    if not name:
        return fail("اسم اللون مطلوب")

    if len(name) > 50:
        return fail("اسم اللون طويل جداً")

    hex_code = (hex_code or "").strip() or None

    if hex_code:
        # a pasted code often arrives without the hash
        if not hex_code.startswith("#"):
            hex_code = "#" + hex_code

        if not HEX_PATTERN.match(hex_code):
            return fail("صيغة اللون غير صحيحة — لازم تكون مثل #1E3A5F")

        # One case, always. "#16A34A" and "#16a34a" are the same colour, and
        # storing both is how "أخضر" and "اخضر فاتح" ended up visually
        # identical while looking different in the list.
        hex_code = hex_code.upper()

        clash = Color.query.filter(Color.hex_code.ilike(hex_code))
        if exclude_id is not None:
            clash = clash.filter(Color.id != exclude_id)

        other = clash.first()
        if other is not None:
            return fail(
                f"نفس كود اللون مستخدم للون \"{other.name}\" — "
                "غيّري الكود أو استخدمي اللون الموجود"
            )

    normalized = normalize_color_name(name)

    query = Color.query
    if exclude_id is not None:
        query = query.filter(Color.id != exclude_id)

    for existing in query.all():
        if normalize_color_name(existing.name) == normalized:
            return fail(f"يوجد لون مشابه مسجّل مسبقاً باسم \"{existing.name}\"")

    return success({
        "name": name,
        "hex_code": hex_code
    })
