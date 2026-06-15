from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from models import db, Color
from flask_login import login_required
from utils.permissions import admin_required


def register_color_routes(app):

    # =========================
    # ADD + LIST
    # =========================
    @app.route("/add-color", methods=["GET", "POST"])
    @login_required
    @admin_required
    def add_color():

        if request.method == "POST":

            name = request.form.get("name", "").strip()

            if not name:
                flash("اسم اللون مطلوب", "danger")
                return redirect(url_for("add_color"))

            if len(name) > 50:
                flash("اسم اللون طويل جداً", "danger")
                return redirect(url_for("add_color"))

            exists = Color.query.filter_by(name=name).first()

            if exists:
                flash("هذا اللون موجود مسبقاً", "warning")
                return redirect(url_for("add_color"))

            db.session.add(Color(name=name))
            db.session.commit()

            flash("تمت إضافة اللون بنجاح", "success")
            return redirect(url_for("add_color"))

        colors = Color.query.order_by(Color.id.desc()).all()

        return render_template("add_color.html", colors=colors)


    # =========================
    # EDIT (MODAL)
    # =========================
    @app.route("/color/<int:color_id>/edit", methods=["POST"])
    @login_required
    @admin_required
    def edit_color(color_id):

        color = Color.query.get_or_404(color_id)

        name = request.form.get("name", "").strip()

        if not name:
            flash("اسم اللون مطلوب", "danger")
            return redirect(url_for("add_color"))

        if len(name) > 50:
            flash("اسم اللون طويل جداً", "danger")
            return redirect(url_for("add_color"))

        exists = Color.query.filter(
            Color.name == name,
            Color.id != color.id
        ).first()

        if exists:
            flash("هذا اللون موجود مسبقاً", "warning")
            return redirect(url_for("add_color"))

        color.name = name
        db.session.commit()

        flash("تم تعديل اللون بنجاح", "success")
        return redirect(url_for("add_color"))


    # =========================
    # DELETE
    # =========================
    @app.route("/color/<int:color_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_color(color_id):

        color = Color.query.get_or_404(color_id)

        db.session.delete(color)
        db.session.commit()

        flash("تم حذف اللون بنجاح", "success")

        return redirect(url_for("add_color"))