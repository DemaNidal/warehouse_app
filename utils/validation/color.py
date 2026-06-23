from .base import success, fail


def validate_color_name(name):

    name = name.strip()

    if not name:
        return fail("اسم اللون مطلوب")

    if len(name) > 50:
        return fail("اسم اللون طويل جداً")

    return success(name)