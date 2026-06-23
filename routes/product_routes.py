from flask import flash, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import os
import uuid
from models import (
    db,
    Product,
    Color,
    InventoryLocation,
    InventoryTransaction,
    Size,
    STOCK_NORMAL,
    STOCK_LOW,
    STOCK_CRITICAL
)
from sqlalchemy.orm import joinedload
from flask_login import login_required, current_user
from utils.activity_logger import log_activity
from utils.permissions import admin_required
from config import RESTORE_IN_PROGRESS
from utils.validation.product import validate_product_form
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

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    @app.route("/add-product", methods=["GET", "POST"])
    @login_required
    @admin_required
    def add_product():
        if RESTORE_IN_PROGRESS:
            flash("System is restoring backup. Try again later.", "warning")
            return redirect(url_for("dashboard"))
        if request.method == "POST":

            image = request.files["image"]
            
            filename = ""
            
            if image and image.filename:
                filename = (
                    str(uuid.uuid4())
                    + "_"
                    + secure_filename(
                        image.filename
                    )
                )
               
                if image and image.filename:

                    if not allowed_file(image.filename):

                        flash(
                            "صيغة الصورة غير مدعومة",
                            "danger"
                        )

                        return redirect(
                            url_for("add_product")
                        )

                image.save(
                    os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        filename
                    )
                )

            result = validate_product_form(request.form)

            if not result.valid:
                flash(result.message, "danger")
                return redirect(url_for("add_product"))

            data = result.data    

            product = Product(
                name=data["name"],
                color_id=data["color_id"],
                size_id=data["size_id"],
                minimum_stock=data["minimum_stock"],
                image=filename
            )

            db.session.add(product)
            db.session.commit()
            log_activity(
                current_user.id,
                "ADD_PRODUCT",
                f"Added product: {product.name}"
            )
            return redirect(
                url_for(
                    "product_details",
                    product_id=product.id
                )
            )

        colors = Color.query.order_by(Color.name).all()
        sizes = Size.query.order_by(Size.name).all()
        

        return render_template(
            "add_product.html",
            colors=colors,
            sizes=sizes
        )


    @app.route("/product/<int:product_id>")
    @login_required
    def product_details(product_id):

        product = (
            Product.query
            .options(
                joinedload(Product.color),
                joinedload(Product.size_data),

                joinedload(Product.locations)
                .joinedload(InventoryLocation.warehouse),

                joinedload(Product.transactions)
                .joinedload(InventoryTransaction.location)
                .joinedload(InventoryLocation.warehouse),

                joinedload(Product.transactions)
                .joinedload(InventoryTransaction.destination_location)
                .joinedload(InventoryLocation.warehouse),

                joinedload(Product.transactions)
                .joinedload(InventoryTransaction.user)
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

        return render_template(
            "product_details.html",
            product=product,
            locations=locations,
            total_quantity=product.total_quantity,
            transactions=transactions,
            stock_status=product.stock_status
        )
    
    @app.route(
    "/product/<int:product_id>/edit",
    methods=["GET", "POST"]
    )
    @login_required
    @admin_required
    def edit_product(product_id):
        if RESTORE_IN_PROGRESS:
            flash("System is restoring backup. Try again later.", "warning")
            return redirect(url_for("dashboard"))
        product = Product.query.get_or_404(
            product_id
        )

        if request.method == "POST":

            product.name = request.form["name"]

            product.size_id = int(request.form["size_id"])

            product.color_id = int(
                request.form["color_id"]
            )
            product.minimum_stock = int(
                request.form["minimum_stock"]
            )

            image = request.files["image"]

            if image and image.filename:

                old_image = product.image

                filename = (
                    str(uuid.uuid4())
                    + "_"
                    + secure_filename(
                        image.filename
                    )
                )
                
                if image and image.filename:

                    if not allowed_file(image.filename):

                        flash(
                            "صيغة الصورة غير مدعومة",
                            "danger"
                        )

                        return redirect(
                            url_for("add_product")
                        )


                image.save(
                    os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        filename
                    )
                )

                product.image = filename

                if old_image:

                    old_path = os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        old_image
                    )

                    if os.path.exists(old_path):
                        os.remove(old_path)
            

            db.session.commit()
            log_activity(
                current_user.id,
                "EDIT_PRODUCT",
                f"Edited product: {product.name}"
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

        sizes = Size.query.order_by(
            Size.name
        ).all()

        return render_template(
            "edit_product.html",
            product=product,
            colors=colors,
            sizes=sizes
        )
    

    @app.route("/products")
    @login_required
    def product_list():

        page = request.args.get("page", 1, type=int)

        products = (
            Product.query
            .options(
                joinedload(Product.color),
                joinedload(Product.size_data)
            )
            .order_by(Product.id.desc())
            .paginate(
                page=page,
                per_page=20,
                error_out=False
            )
        )

        return render_template(
            "product_list.html",
            products=products
        )

