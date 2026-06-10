from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)
from models import (
    db,
    Product,
    Warehouse,
    InventoryLocation
)
from flask_login import login_required


def register_location_routes(app):

    @app.route(
        "/product/<int:product_id>/add-location",
        methods=["GET", "POST"]
    )
    @login_required
    def add_location(product_id):

        product = Product.query.get_or_404(
            product_id
        )

        if request.method == "POST":

            location = InventoryLocation(

                product_id=product.id,

                warehouse_id=request.form[
                    "warehouse_id"
                ],

                location=request.form[
                    "location"
                ],

                quantity=request.form[
                    "quantity"
                ]
            )

            db.session.add(location)

            db.session.commit()

            return redirect(
                f"/product/{product.id}"
            )

        warehouses = Warehouse.query.order_by(
            Warehouse.name
        ).all()

        return render_template(
            "add_location.html",
            product=product,
            warehouses=warehouses
        )
    

    @app.route(
        "/location/<int:location_id>/edit",
        methods=["GET", "POST"]
    )
    @login_required
    def edit_location(location_id):

        location = InventoryLocation.query.get_or_404(
            location_id
        )

        if request.method == "POST":

            location.location = request.form["location"]

            

            db.session.commit()

            return redirect(
                url_for(
                    "product_details",
                    product_id=location.product_id
                )
            )

        return render_template(
            "edit_location.html",
            location=location
        )
    
    @app.route(
    "/location/<int:location_id>/delete",
    methods=["POST"]
    )
    @login_required
    def delete_location(location_id):

        location = InventoryLocation.query.get_or_404(
            location_id
        )

        product_id = location.product_id

        if location.quantity > 0:

            flash(
                "لا يمكن حذف موقع يحتوي على كمية",
                "danger"
            )

            return redirect(
                url_for(
                    "product_details",
                    product_id=product_id
                )
            )

        db.session.delete(location)

        db.session.commit()

        flash(
            "تم حذف الموقع بنجاح",
            "success"
        )

        return redirect(
            url_for(
                "product_details",
                product_id=product_id
            )
        )