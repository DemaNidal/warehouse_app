from .base import success, fail


def validate_warehouse_name(name):

    name = name.strip()

    if not name:
        return fail("اسم المستودع مطلوب")

    if len(name) > 100:
        return fail("اسم المستودع طويل جداً")

    return success(name)
