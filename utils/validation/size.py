from .base import success, fail


def validate_size_name(name):

    name = name.strip()

    if not name:
        return fail("الحجم مطلوب")

    if len(name) > 50:
        return fail("اسم الحجم طويل جداً")

    return success(name)