from .base import success, fail


def validate_restore(secret, file, expected_secret):

    if not secret:
        return fail("Restore secret is required")

    if secret != expected_secret:
        return fail("Invalid restore secret")

    if not file:
        return fail("Backup file required")

    if not file.filename.endswith(".zip"):
        return fail("Backup must be ZIP")

    return success()