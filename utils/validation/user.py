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


VALID_ROLES = ["ADMIN", "STORE_MANAGER", "EMPLOYEE"]


def validate_add_user(username, password, confirm_password, role):

    username_result = validate_username(username)

    if not username_result.valid:
        return username_result

    password_result = validate_password(password)

    if not password_result.valid:
        return password_result

    if password != confirm_password:
        return fail("كلمتا المرور غير متطابقتين")

    if role not in VALID_ROLES:
        return fail("صلاحية غير صالحة")

    return success({
        "username": username_result.data,
        "password": password,
        "role": role
    })


def validate_edit_user(username, role):

    username_result = validate_username(username)

    if not username_result.valid:
        return username_result

    if role not in VALID_ROLES:
        return fail("صلاحية غير صالحة")

    return success({
        "username": username_result.data,
        "role": role
    })