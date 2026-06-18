from functools import wraps

from flask_login import (
    current_user
)

from flask import (
    abort
)


def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not current_user.is_authenticated:

            abort(403)

        if current_user.role != "ADMIN":

            abort(403)

        return func(
            *args,
            **kwargs
        )

    return wrapper

def manager_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if not current_user.is_authenticated:
            abort(403)

        if current_user.role not in [
            "ADMIN",
            "STORE_MANAGER"
        ]:
            abort(403)

        return func(*args, **kwargs)

    return wrapper