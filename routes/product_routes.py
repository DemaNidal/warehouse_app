from flask import flash, render_template, request, redirect, url_for
import os
from models import (
    db,
    Product,
    Category,
    Color,
    InventoryLocation,
    InventoryTransaction,
    Size,
    Warehouse,
    SIZE_KIND_CAPACITY,
    SIZE_KIND_NECK,
    STOCK_NORMAL,
    STOCK_LOW,
    STOCK_CRITICAL
)
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from flask_login import login_required, current_user
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.product import validate_product_form
from utils.images import optimize_upload, ImageError
from utils.storage import save_image, delete_image
from utils.search_text import refresh_search_text
from utils.catalogue import browse_flat
from utils.transaction_undo import compute_undoable_transaction_ids
ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}
def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower() in ALLOWED_EXTENSIONS
    )

def find_exact_twin(name, color_id, size_id, neck_size_id, exclude_id=None):
    """A product identical in every field that identifies one.

    Same name alone is not a duplicate — the same cap comes in six colours
    and each is its own product. Only when the name, colour, capacity and
    neck all match is a second row the same item entered twice.
    """
    from utils.categorization import normalize

    query = Product.query.filter(
        Product.color_id == color_id,
        Product.size_id.is_(None) if size_id is None else Product.size_id == size_id,
        Product.neck_size_id.is_(None) if neck_size_id is None
        else Product.neck_size_id == neck_size_id,
    )
    if exclude_id:
        query = query.filter(Product.id != exclude_id)

    wanted = normalize(name)
    for candidate in query.all():
        if normalize(candidate.name) == wanted:
            return candidate
    return None


def register_product_routes(app):

    # only the local backend writes here; on object storage this would just
    # leave an empty folder behind on every start
    if os.getenv("STORAGE_BACKEND", "local").strip().lower() == "local":
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    @app.route("/add-product", methods=["GET", "POST"])
    @login_required
    @manager_required
    def add_product():
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))
        if request.method == "POST":

            # Validate before touching object storage. The upload used to come
            # first, so a form that failed validation still left its photo in
            # the bucket with no product pointing at it.
            result = validate_product_form(request.form)

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("add_product"))

            data = result.data

            # The form asks for confirmation before sending an exact twin;
            # this is the backstop for a double-click that fires two
            # identical requests before the first has landed, and for a
            # browser with scripts off.
            if request.form.get("confirm_duplicate") != "1":
                twin = find_exact_twin(
                    data["name"], data["color_id"],
                    data["size_id"], data["neck_size_id"],
                )
                if twin is not None:
                    flash(
                        f"في منتج بنفس الاسم واللون والمقاس بالظبط: "
                        f"«{twin.name}» (#{twin.id}). ما انحفظ.",
                        "warning",
                    )
                    return redirect(url_for("product_details", product_id=twin.id))

            image = request.files.get("image")

            filename = ""

            if image and image.filename:

                if not allowed_file(image.filename):
                    flash("صيغة الصورة غير مدعومة", "danger")
                    return redirect(url_for("add_product"))

                try:
                    optimized, filename = optimize_upload(image)
                except ImageError as exc:
                    flash(str(exc), "danger")
                    return redirect(url_for("add_product"))

                save_image(optimized, filename)

            product = Product(
                name=data["name"],
                color_id=data["color_id"],
                secondary_color_id=data["secondary_color_id"],
                size_id=data["size_id"],
                neck_size_id=data["neck_size_id"],
                category_id=data["category_id"],
                minimum_stock=data["minimum_stock"],
                image=filename
            )

            db.session.add(product)

            try:
                # flush first so the colour/size/category relationships resolve,
                # then build the searchable text from them
                db.session.flush()
                refresh_search_text(product)

                db.session.commit()
            except Exception:
                # The row is gone but the photo is already in the bucket, so
                # take it back out rather than leave it orphaned.
                db.session.rollback()
                if filename:
                    delete_image(filename)
                raise

            log_activity(
                current_user.id,
                "ADD_PRODUCT",
                f"اضافة المنتج: {product.name}"
            )
            return redirect(
                url_for(
                    "product_details",
                    product_id=product.id
                )
            )

        colors = Color.query.order_by(Color.name).all()
        capacities = Size.query.filter_by(kind=SIZE_KIND_CAPACITY).order_by(Size.name).all()
        neck_sizes = Size.query.filter_by(kind=SIZE_KIND_NECK).order_by(Size.name).all()
        categories = Category.query.order_by(
            Category.sort_order,
            Category.id
        ).all()

        return render_template(
            "add_product.html",
            colors=colors,
            capacities=capacities,
            neck_sizes=neck_sizes,
            categories=categories
        )


    @app.route("/products/duplicate-check")
    @login_required
    def duplicate_check():
        """Does an identical product already exist? Asked by the add form
        before it submits, so the person can decide with the form intact."""

        name = request.args.get("name", "").strip()
        color_id = request.args.get("color_id", type=int)
        size_id = request.args.get("size_id", type=int)
        neck_size_id = request.args.get("neck_size_id", type=int)

        if not name or not color_id:
            return {"duplicate": False}

        twin = find_exact_twin(name, color_id, size_id, neck_size_id)
        if twin is None:
            return {"duplicate": False}

        return {
            "duplicate": True,
            "id": twin.id,
            "name": twin.name,
            "quantity": twin.total_quantity,
            "url": url_for("product_details", product_id=twin.id),
        }

    @app.route("/product/<int:product_id>")
    @login_required
    def product_details(product_id):

        product = (
            Product.query
            .options(
                joinedload(Product.color),
                joinedload(Product.secondary_color),
                joinedload(Product.size_data),
                joinedload(Product.neck_size),
                joinedload(Product.category),

                joinedload(Product.locations)
                .joinedload(InventoryLocation.warehouse),

                joinedload(Product.transactions)
                .joinedload(InventoryTransaction.location)
                .joinedload(InventoryLocation.warehouse),

                joinedload(Product.transactions)
                .joinedload(InventoryTransaction.destination_location)
                .joinedload(InventoryLocation.warehouse),

                joinedload(Product.transactions)
                .joinedload(InventoryTransaction.user),

                joinedload(Product.transactions)
                .joinedload(InventoryTransaction.customer)
            )
            .filter_by(id=product_id)
            .first_or_404()
        )

        locations = product.locations

        
        

        transactions = sorted(
            product.transactions,
            key=lambda t: t.created_at,
            reverse=True
        )

        undoable_ids = compute_undoable_transaction_ids(transactions)

        return render_template(
            "product_details.html",
            product=product,
            locations=locations,
            total_quantity=product.total_quantity,
            transactions=transactions,
            stock_status=product.stock_status,
            undoable_ids=undoable_ids
        )
    
    @app.route(
    "/product/<int:product_id>/edit",
    methods=["GET", "POST"]
    )
    @login_required
    @manager_required
    def edit_product(product_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))
        product = Product.query.get_or_404(
            product_id
        )

        if request.method == "POST":

            result = validate_product_form(request.form)

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("edit_product", product_id=product.id))

            data = result.data

            product.name = data["name"]
            product.size_id = data["size_id"]
            product.neck_size_id = data["neck_size_id"]
            product.category_id = data["category_id"]
            product.color_id = data["color_id"]
            product.secondary_color_id = data["secondary_color_id"]
            product.minimum_stock = data["minimum_stock"]

            image = request.files.get("image")

            filename = ""
            old_image = ""

            if image and image.filename:

                if not allowed_file(image.filename):
                    flash("صيغة الصورة غير مدعومة", "danger")
                    return redirect(
                        url_for("edit_product", product_id=product.id)
                    )

                try:
                    optimized, filename = optimize_upload(image)
                except ImageError as exc:
                    flash(str(exc), "danger")
                    return redirect(
                        url_for("edit_product", product_id=product.id)
                    )

                old_image = product.image or ""

                save_image(optimized, filename)
                product.image = filename

            # The flush is inside the guard too: a bad foreign key raises there
            # rather than at commit, and that path also has an upload to undo.
            try:
                db.session.flush()

                # The colour, size and category are assigned by id above. An
                # already-loaded relationship does not follow its foreign key,
                # so expire them and let the next read come from the row that
                # was just written — otherwise the search index keeps the old
                # colour.
                db.session.expire(product, [
                    "color", "secondary_color", "category",
                    "size_data", "neck_size",
                ])
                refresh_search_text(product)

                db.session.commit()
            except Exception:
                # The save failed, so the row still points at the old file.
                # Drop the replacement that was just uploaded — deleting the
                # old one here instead would leave the product with a filename
                # whose file no longer exists.
                db.session.rollback()
                if filename:
                    delete_image(filename)
                raise

            # Only now is the new filename actually stored. Removing the old
            # file before the commit would destroy the image a rolled-back
            # product still refers to.
            if old_image and old_image != product.image:
                delete_image(old_image)

            log_activity(
                current_user.id,
                "EDIT_PRODUCT",
                f"تعديل المنتج: {product.name}"
            )

            return redirect(
                url_for(
                    "product_details",
                    product_id=product.id
                )
            )

        colors = Color.query.order_by(
            Color.name
        ).all()

        capacities = Size.query.filter_by(
            kind=SIZE_KIND_CAPACITY
        ).order_by(Size.name).all()

        neck_sizes = Size.query.filter_by(
            kind=SIZE_KIND_NECK
        ).order_by(Size.name).all()

        categories = Category.query.order_by(
            Category.sort_order,
            Category.id
        ).all()

        return render_template(
            "edit_product.html",
            product=product,
            colors=colors,
            capacities=capacities,
            neck_sizes=neck_sizes,
            categories=categories
        )
    

    @app.route("/products")
    @login_required
    def product_list():

        page = request.args.get("page", 1, type=int)
        stock_filter = request.args.get("stock", "")
        category_filter = request.args.get("category", "")
        warehouse_filter = request.args.get("warehouse", "")
        sort = request.args.get("sort", "recent")

        # one card per product
        (pagination, units, category_filter, stock_filter,
         warehouse_filter, sort) = browse_flat(
            category_filter=category_filter,
            stock_filter=stock_filter,
            warehouse_filter=warehouse_filter,
            sort=sort,
            page=page,
        )

        categories = Category.query.order_by(
            Category.sort_order,
            Category.id
        ).all()

        uncategorized_count = Product.query.filter(
            Product.category_id.is_(None)
        ).count()

        return render_template(
            "product_list.html",
            products=pagination,
            units=units,
            stock_filter=stock_filter,
            category_filter=category_filter,
            warehouse_filter=warehouse_filter,
            warehouses=Warehouse.query.order_by(Warehouse.name).all(),
            categories=categories,
            uncategorized_count=uncategorized_count,
            sort=sort
        )

