from .base import success, fail
from models import TRANSACTION_TYPES


def validate_transaction(form):

    transaction_type = form.get("transaction_type")

    if transaction_type not in TRANSACTION_TYPES:
        return fail("نوع الحركة غير صحيح")

    try:
        location_id = int(form["location_id"])
        quantity = int(form["quantity"])
    except Exception:
        return fail("بيانات غير صحيحة")

    if quantity <= 0:
        return fail("الكمية يجب أن تكون أكبر من صفر")

    notes = form.get("notes", "").strip()

    return success({
        "transaction_type": transaction_type,
        "location_id": location_id,
        "quantity": quantity,
        "notes": notes
    })