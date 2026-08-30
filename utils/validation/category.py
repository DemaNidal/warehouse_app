from .base import success, fail
from models import Category
from utils.categorization import normalize


def validate_category_name(name, icon=None, exclude_id=None):

    name = name.strip()

    if not name:
        return fail("اسم التصنيف مطلوب")

    if len(name) > 100:
        return fail("اسم التصنيف طويل جداً")

    icon = (icon or "").strip() or None

    if icon and len(icon) > 50:
        return fail("اسم الأيقونة طويل جداً")

    normalized = normalize(name)

    query = Category.query
    if exclude_id is not None:
        query = query.filter(Category.id != exclude_id)

    for existing in query.all():
        if normalize(existing.name) == normalized:
            return fail("هذا التصنيف موجود مسبقاً")

    return success({
        "name": name,
        "icon": icon
    })
