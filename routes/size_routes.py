from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from models import db, Size
from flask_login import current_user, login_required
from routes.backup_routes import RESTORE_IN_PROGRESS
from utils.activity_logger import log_activity
from utils.permissions import admin_required


def register_size_routes(app):

    # =========================
    # ADD + LIST
    # =========================
    @app.route("/add-size", methods=["GET", "POST"])
    @login_required
    @admin_required
    def add_size():
        if RESTORE_IN_PROGRESS:
            flash("System is restoring backup. Try again later.", "warning")
            return redirect(url_for("dashboard"))
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

            size = Size(name=name)

            db.session.add(size)
            db.session.commit()

            log_activity(
                current_user.id,
                "ADD_SIZE",
                f"Added size: {size.name}"
            )

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
        if RESTORE_IN_PROGRESS:
            flash("System is restoring backup. Try again later.", "warning")
            return redirect(url_for("dashboard"))
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
        log_activity(
            current_user.id,
            "EDIT_SIZE",
            f"Edited size: {size.name}"
        )
        return redirect(url_for("add_size"))


    # =========================
    # DELETE
    # =========================
    # @app.route("/size/<int:size_id>/delete", methods=["POST"])
    # @login_required
    # @admin_required
    # def delete_size(size_id):

    #     size = Size.query.get_or_404(size_id)

    #     db.session.delete(size)
    #     db.session.commit()

    #     flash("تم حذف الحجم بنجاح", "success")
    #     log_activity(
    #         current_user.id,
    #         "DELETE_SIZE",
    #         f"Deleted size: {size.name}"
    #     )

    #     return redirect(url_for("add_size"))