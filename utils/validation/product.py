from .base import success, fail


def validate_product_form(form):

    name = form.get("name", "").strip()

    if not name:
        return fail("اسم المنتج مطلوب")

    if len(name) > 150:
        return fail("اسم المنتج طويل جداً")

    try:
        color_id = int(form["color_id"])
        minimum_stock = int(form["minimum_stock"])
    except Exception:
        return fail("بيانات المنتج غير صحيحة")

    # A cap has a neck size and no capacity; a bottle has a capacity and
    # (once recorded) a neck size. Either may be blank, but not both.
    def optional_int(field, label):
        raw = form.get(field, "").strip()
        if not raw:
            return None, None
        try:
            return int(raw), None
        except ValueError:
            return None, fail(label)

    size_id, err = optional_int("size_id", "السعة غير صحيحة")
    if err:
        return err

    neck_size_id, err = optional_int("neck_size_id", "مقاس الرقبة غير صحيح")
    if err:
        return err

    if size_id is None and neck_size_id is None:
        return fail("لازم تختار السعة أو مقاس الرقبة على الأقل")

    if minimum_stock < 0:
        return fail("الحد الأدنى لا يمكن أن يكون سالباً")

    # Optional so the 91 products entered before categories existed can still
    # be saved from the edit form without forcing a choice.
    raw_category_id = form.get("category_id", "").strip()
    category_id = None

    if raw_category_id:
        try:
            category_id = int(raw_category_id)
        except ValueError:
            return fail("التصنيف غير صحيح")

    raw_secondary_color_id = form.get("secondary_color_id", "").strip()
    secondary_color_id = None

    if raw_secondary_color_id:
        try:
            secondary_color_id = int(raw_secondary_color_id)
        except ValueError:
            return fail("اللون الثاني غير صحيح")

        if secondary_color_id == color_id:
            return fail("لا يمكن اختيار نفس اللون مرتين")

    return success({
        "name": name,
        "color_id": color_id,
        "secondary_color_id": secondary_color_id,
        "size_id": size_id,
        "neck_size_id": neck_size_id,
        "category_id": category_id,
        "minimum_stock": minimum_stock
    })