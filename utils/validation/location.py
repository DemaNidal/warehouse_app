from .base import fail, success

def validate_location(form):
    warehouse_id = form.get("warehouse_id")
    quantity = form.get("quantity")
    location = form.get("location", "").strip()

    if not warehouse_id:
        return fail("المستودع مطلوب")

    if not quantity:
        return fail("الكمية مطلوبة")

    try:
        quantity = int(quantity)
    except ValueError:
        return fail("الكمية غير صحيحة")

    if quantity < 0:
        return fail("الكمية لا يمكن أن تكون سالبة")

    return success({
        "warehouse_id": int(warehouse_id),
        "quantity": quantity,
        "location": location or None
    })