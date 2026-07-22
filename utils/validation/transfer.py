from .base import success, fail


def validate_transfer(form):

    try:
        source = int(form["source_location_id"])
        destination = int(form["destination_location_id"])
        quantity = int(form["quantity"])
    except Exception:
        return fail("بيانات التحويل غير صحيحة")

    if source == destination:
        return fail("لا يمكن التحويل لنفس الموقع")

    if quantity <= 0:
        return fail("الكمية يجب أن تكون أكبر من صفر")

    return success({
        "source": source,
        "destination": destination,
        "quantity": quantity,
        "notes": form.get("notes", "").strip(),
        "quantity_expression": form.get("quantity_expression", "").strip()[:255] or None
    })