from flask import render_template, request, redirect
from models import db, Color
from flask_login import login_required

def register_color_routes(app):

    @app.route("/add-color", methods=["GET", "POST"])
    @login_required
    def add_color():

        if request.method == "POST":

            color_name = request.form["name"].strip()

            if color_name:

                exists = Color.query.filter_by(
                    name=color_name
                ).first()

                if not exists:
                    color = Color(name=color_name)

                    db.session.add(color)
                    db.session.commit()

            return redirect("/add-color")

        colors = Color.query.order_by(Color.name).all()

        return render_template(
            "add_color.html",
            colors=colors
        )