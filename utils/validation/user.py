from .base import success, fail


def validate_username(username):

    username = username.strip()

    if not username:
        return fail("اسم المستخدم مطلوب")

    if len(username) < 3:
        return fail("اسم المستخدم قصير")

    if len(username) > 50:
        return fail("اسم المستخدم طويل")

    return success(username)


def validate_password(password):

    if len(password) < 6:
        return fail("كلمة المرور قصيرة")

    return success(password)