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

    customer_id = None

    if transaction_type == "OUT":

        raw_customer_id = form.get("customer_id", "").strip()

        if not raw_customer_id:
            return fail("يجب اختيار العميل عند الإخراج")

        try:
            customer_id = int(raw_customer_id)
        except ValueError:
            return fail("العميل غير صحيح")

    return success({
        "transaction_type": transaction_type,
        "location_id": location_id,
        "quantity": quantity,
        "notes": notes,
        "customer_id": customer_id,
        "quantity_expression": form.get("quantity_expression", "").strip()[:255] or None
    })