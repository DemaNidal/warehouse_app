from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from models import db, Size
from flask_login import login_required
from utils.permissions import admin_required


def register_size_routes(app):

    # =========================
    # ADD + LIST
    # =========================
    @app.route("/add-size", methods=["GET", "POST"])
    @login_required
    @admin_required
    def add_size():

        if request.method == "POST":

            name = request.form.get("name", "").strip()

            if not name:
                flash("الحجم مطلوب", "danger")
                return redirect(url_for("add_size"))

            if len(name) > 50:
                flash("اسم الحجم طويل جداً", "danger")
                return redirect(url_for("add_size"))

            exists = Size.query.filter_by(name=name).first()

            if exists:
                flash("هذا الحجم موجود مسبقاً", "warning")
                return redirect(url_for("add_size"))

            db.session.add(Size(name=name))
            db.session.commit()

            flash("تمت إضافة الحجم بنجاح", "success")
            return redirect(url_for("add_size"))

        sizes = Size.query.order_by(Size.id.desc()).all()

        return render_template("add_size.html", sizes=sizes)


    # =========================
    # EDIT (MODAL POST ONLY)
    # =========================
    @app.route("/size/<int:size_id>/edit", methods=["POST"])
    @login_required
    @admin_required
    def edit_size(size_id):

        size = Size.query.get_or_404(size_id)

        name = request.form.get("name", "").strip()

        if not name:
            flash("الحجم مطلوب", "danger")
            return redirect(url_for("add_size"))

        if len(name) > 50:
            flash("اسم الحجم طويل جداً", "danger")
            return redirect(url_for("add_size"))

        exists = Size.query.filter(
            Size.name == name,
            Size.id != size.id
        ).first()

        if exists:
            flash("هذا الحجم موجود مسبقاً", "warning")
            return redirect(url_for("add_size"))

        size.name = name
        db.session.commit()

        flash("تم تعديل الحجم بنجاح", "success")
        return redirect(url_for("add_size"))


    # =========================
    # DELETE
    # =========================
    @app.route("/size/<int:size_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_size(size_id):

        size = Size.query.get_or_404(size_id)

        db.session.delete(size)
        db.session.commit()

        flash("تم حذف الحجم بنجاح", "success")

        return redirect(url_for("add_size"))