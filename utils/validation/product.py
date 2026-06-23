from .base import success, fail


def validate_product_form(form):

    name = form.get("name", "").strip()

    if not name:
        return fail("اسم المنتج مطلوب")

    if len(name) > 150:
        return fail("اسم المنتج طويل جداً")

    try:
        color_id = int(form["color_id"])
        size_id = int(form["size_id"])
        minimum_stock = int(form["minimum_stock"])
    except Exception:
        return fail("بيانات المنتج غير صحيحة")

    if minimum_stock < 0:
        return fail("الحد الأدنى لا يمكن أن يكون سالباً")

    return success({
        "name": name,
        "color_id": color_id,
        "size_id": size_id,
        "minimum_stock": minimum_stock
    })