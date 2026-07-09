import hmac

from .base import success, fail


def validate_bootstrap_admin(secret, username, password, confirm_password, expected_secret):

    if not expected_secret:
        return fail("BOOTSTRAP_ADMIN_SECRET غير مضبوط على السيرفر")

    if not secret or not hmac.compare_digest(secret, expected_secret):
        return fail("الرمز السري غير صحيح")

    username = (username or "").strip()

    if not username:
        return fail("اسم المستخدم مطلوب")

    if not password or len(password) < 8:
        return fail("كلمة المرور يجب أن تكون 8 أحرف على الأقل")

    if password != confirm_password:
        return fail("كلمتا المرور غير متطابقتين")

    return success({
        "username": username,
        "password": password
    })
