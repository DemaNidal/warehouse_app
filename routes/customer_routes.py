from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

from models import db, Customer, InventoryTransaction, StockRequest
from flask_login import current_user, login_required
from utils.activity_logger import log_activity
from utils.permissions import admin_required, manager_required
from utils.system_guard import ensure_system_ready
from utils.validation.customer import validate_customer_name
from sqlalchemy.exc import IntegrityError

def register_customer_routes(app):

    # =========================
    # SEARCH CUSTOMERS (AJAX)
    # =========================
    @app.route("/customers/search")
    @login_required
    @manager_required
    def search_customers():

        if not ensure_system_ready():
            return jsonify(success=False, message="النظام قيد الاسترجاع حالياً"), 503

        query_text = request.args.get("q", "").strip()
        limit = min(max(int(request.args.get("limit", 10, type=int)), 1), 20)

        base_query = Customer.query

        if query_text:
            base_query = base_query.filter(Customer.name.ilike(f"%{query_text}%"))

        customers = base_query.order_by(Customer.name).limit(limit).all()

        return jsonify([
            {"id": customer.id, "name": customer.name}
            for customer in customers
        ])

    # =========================
    # ADD + LIST
    # =========================
    @app.route("/add-customer", methods=["GET", "POST"])
    @login_required
    @manager_required
    def add_customer():

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if not ensure_system_ready():
            if is_ajax:
                return jsonify(success=False, message="النظام قيد الاسترجاع حالياً"), 503
            return redirect(url_for("dashboard"))

        if request.method == "POST":

            result = validate_customer_name(request.form.get("name", ""))

            if not result.valid:
                if is_ajax:
                    return jsonify(success=False, message=result.message), 400
                flash(result.message, "danger")
                return redirect(url_for("add_customer"))

            name = result.data

            exists = Customer.query.filter_by(name=name).first()
            if exists:
                if is_ajax:
                    return jsonify(success=False, message="هذا العميل موجود مسبقاً"), 409
                flash("هذا العميل موجود مسبقاً", "warning")
                return redirect(url_for("add_customer"))

            customer = Customer(name=name)

            try:
                db.session.add(customer)
                db.session.commit()

                log_activity(
                    current_user.id,
                    "ADD_CUSTOMER",
                    f"اضافة العميل: {customer.name}"
                )

                if is_ajax:
                    return jsonify(success=True, id=customer.id, name=customer.name)

                flash("تمت إضافة العميل بنجاح", "success")

            except IntegrityError:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="هذا العميل موجود مسبقاً"), 409
                flash("هذا العميل موجود مسبقاً (DB)", "warning")

            except Exception:
                db.session.rollback()
                if is_ajax:
                    return jsonify(success=False, message="حدث خطأ أثناء الحفظ"), 500
                flash("حدث خطأ أثناء الحفظ", "danger")

            return redirect(url_for("add_customer"))

        customers = Customer.query.order_by(Customer.id.desc()).all()

        used_from_transactions = {
            row[0] for row in db.session.query(InventoryTransaction.customer_id)
            .filter(InventoryTransaction.customer_id.isnot(None)).distinct()
        }
        used_from_requests = {
            row[0] for row in db.session.query(StockRequest.customer_id)
            .filter(StockRequest.customer_id.isnot(None)).distinct()
        }
        used_customer_ids = used_from_transactions | used_from_requests

        return render_template(
            "add_customer.html",
            customers=customers,
            used_customer_ids=used_customer_ids
        )


    # =========================
    # EDIT (MODAL)
    # =========================
    @app.route("/customer/<int:customer_id>/edit", methods=["POST"])
    @login_required
    @admin_required
    def edit_customer(customer_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        customer = Customer.query.get_or_404(customer_id)

        result = validate_customer_name(request.form.get("name", ""))

        if not result.valid:
            flash(result.message, "danger")
            return redirect(url_for("add_customer"))

        name = result.data

        exists = Customer.query.filter(
            Customer.name == name,
            Customer.id != customer.id
        ).first()

        if exists:
            flash("هذا العميل موجود مسبقاً", "warning")
            return redirect(url_for("add_customer"))

        customer.name = name
        db.session.commit()
        log_activity(
            current_user.id,
            "EDIT_CUSTOMER",
            f"تعديل العميل: {customer.name}"
        )

        flash("تم تعديل العميل بنجاح", "success")
        return redirect(url_for("add_customer"))


    # =========================
    # DELETE
    # =========================
    @app.route("/customer/<int:customer_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def delete_customer(customer_id):

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        customer = Customer.query.get_or_404(customer_id)

        in_use = (
            InventoryTransaction.query.filter_by(customer_id=customer.id).first() is not None
            or StockRequest.query.filter_by(customer_id=customer.id).first() is not None
        )

        if in_use:
            flash("لا يمكن حذف عميل له حركات أو طلبات مسجلة", "danger")
            return redirect(url_for("add_customer"))

        name = customer.name

        db.session.delete(customer)
        db.session.commit()

        log_activity(
            current_user.id,
            "DELETE_CUSTOMER",
            f"حذف العميل: {name}"
        )

        flash("تم حذف العميل بنجاح", "success")
        return redirect(url_for("add_customer"))
