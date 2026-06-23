from .base import success, fail


def validate_login(username, password):

    username = username.strip()

    if not username:
        return fail("اسم المستخدم مطلوب")

    if not password:
        return fail("كلمة المرور مطلوبة")

    return success({
        "username": username,
        "password": password
    })