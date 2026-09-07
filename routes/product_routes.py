from flask import flash, render_template, request, redirect, url_for
import os
from models import (
    db,
    Product,
    Category,
    Color,
    InventoryLocation,
    InventoryTransaction,
    ProductFamily,
    Size,
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
from utils.families import find_match
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

            image = request.files.get("image")

            filename = ""

            if image and image.filename:

                if not allowed_file(image.filename):
                    flash("صيغة الصورة غير مدعومة", "danger")
                    return redirect(url_for("add_product"))

                try:
                    data, filename = optimize_upload(image)
                except ImageError as exc:
                    flash(str(exc), "danger")
                    return redirect(url_for("add_product"))

                save_image(data, filename)

            result = validate_product_form(request.form)

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("add_product"))

            data = result.data    

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

            # flush first so the colour/size/category relationships resolve,
            # then build the searchable text from them
            db.session.flush()
            refresh_search_text(product)

            db.session.commit()
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
                joinedload(Product.family)
                .joinedload(ProductFamily.variants)
                .joinedload(Product.color),

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

        # offered as link targets when this product is not in a family yet
        families = (
            ProductFamily.query.order_by(ProductFamily.name).all()
            if product.family_id is None else []
        )

        # another product with the same name, if there is one and the pairing
        # has not already been turned down
        match = find_match(product) if product.family_id is None else None

        return render_template(
            "product_details.html",
            product=product,
            families=families,
            match=match,
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

            if image and image.filename:

                if not allowed_file(image.filename):
                    flash("صيغة الصورة غير مدعومة", "danger")
                    return redirect(
                        url_for("edit_product", product_id=product.id)
                    )

                try:
                    data, filename = optimize_upload(image)
                except ImageError as exc:
                    flash(str(exc), "danger")
                    return redirect(
                        url_for("edit_product", product_id=product.id)
                    )

                old_image = product.image

                save_image(data, filename)
                product.image = filename

                # only drop the previous file once the new one is stored
                if old_image:
                    delete_image(old_image)

            db.session.flush()

            # The colour, size and category are assigned by id above. An
            # already-loaded relationship does not follow its foreign key, so
            # expire them and let the next read come from the row that was just
            # written — otherwise the search index can keep the old colour.
            db.session.expire(product, [
                "color", "secondary_color", "category",
                "size_data", "neck_size", "family",
            ])
            refresh_search_text(product)

            db.session.commit()
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
        sort = request.args.get("sort", "recent")

        # one card per product. Families are shown on their own pages, not by
        # collapsing this list.
        pagination, units, category_filter, stock_filter, sort = browse_flat(
            category_filter=category_filter,
            stock_filter=stock_filter,
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
            categories=categories,
            uncategorized_count=uncategorized_count,
            sort=sort
        )

