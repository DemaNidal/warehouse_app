from .base import success, fail


def validate_customer_name(name):

    name = name.strip()

    if not name:
        return fail("اسم العميل مطلوب")

    if len(name) > 150:
        return fail("اسم العميل طويل جداً")

    return success(name)
