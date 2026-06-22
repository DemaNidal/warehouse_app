class ValidationResult:
    def __init__(self, ok: bool, data=None, error=None):
        self.ok = ok
        self.data = data
        self.error = error


def fail(msg):
    return ValidationResult(False, error=msg)


def success(data):
    return ValidationResult(True, data=data)