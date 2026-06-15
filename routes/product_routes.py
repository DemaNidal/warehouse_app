from flask import render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import os
import uuid
from models import (
    db,
    Product,
    Color,
    InventoryLocation,
    InventoryTransaction,
    Size
)
from flask_login import login_required
from utils.permissions import admin_required

def register_product_routes(app):

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    @app.route("/add-product", methods=["GET", "POST"])
    @login_required
    @admin_required
    def add_product():

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

                image.save(
                    os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        filename
                    )
                )

            product = Product(
                name=request.form["name"],
                size_id=request.form["size_id"],
                image=filename,
                color_id=request.form["color_id"]
            )

            db.session.add(product)
            db.session.commit()

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

        product = Product.query.get_or_404(product_id)

        locations = InventoryLocation.query.filter_by(
            product_id=product.id
        ).all()

        total_quantity = sum(
        location.quantity
        for location in locations
        )

        transactions = (
            InventoryTransaction.query
            .filter_by(product_id=product.id)
            .order_by(
                InventoryTransaction.created_at.desc()
            )
            .all()
        )
        
        return render_template(
            "product_details.html",
            product=product,
            locations=locations,
            total_quantity=total_quantity,
            transactions=transactions
        )
    
    @app.route(
    "/product/<int:product_id>/edit",
    methods=["GET", "POST"]
    )
    @login_required
    @admin_required
    def edit_product(product_id):

        product = Product.query.get_or_404(
            product_id
        )

        if request.method == "POST":

            product.name = request.form["name"]

            product.size = request.form["size"]

            product.color_id = int(
                request.form["color_id"]
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

            return redirect(
                url_for(
                    "product_details",
                    product_id=product.id
                )
            )

        colors = Color.query.order_by(
            Color.name
        ).all()

        return render_template(
            "edit_product.html",
            product=product,
            colors=colors
        )
    

    @app.route("/products")
    @login_required
    def product_list():

        products = Product.query.order_by(
            Product.id.desc()
        ).all()

        return render_template(
            "product_list.html",
            products=products
        )

