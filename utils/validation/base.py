from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    message: str = ""
    data: dict | None = None


def success(data=None):
    return ValidationResult(
        valid=True,
        data=data
    )


def fail(message):
    return ValidationResult(
        valid=False,
        message=message
    )