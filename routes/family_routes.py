# -*- coding: utf-8 -*-
"""Grouping products into families.

Every route here is a decision the user makes. Nothing groups anything on its
own — see utils/families.py for why.
"""

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from models import db, InventoryLocation, Product, ProductFamily
from utils.activity_logger import log_activity
from utils.families import (
    suggest_families,
    create_family,
    link_product,
    unlink_product,
    dismiss_suggestion,
    find_match,
    rename_family,
)
from utils.permissions import manager_required
from utils.system_guard import ensure_system_ready


def register_family_routes(app):

    @app.route("/families/suggestions")
    @login_required
    @manager_required
    def family_suggestions():
        proposals = suggest_families()

        return render_template(
            "family_suggestions.html",
            proposals=proposals,
            grouped_count=Product.query.filter(
                Product.family_id.isnot(None)
            ).count(),
            family_count=ProductFamily.query.count(),
        )

    @app.route("/families/suggestions/approve", methods=["POST"])
    @login_required
    @manager_required
    def approve_family_suggestion():
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        name = request.form.get("name", "").strip()
        product_ids = request.form.getlist("product_ids", type=int)

        if not name:
            flash("اسم المجموعة مطلوب", "danger")
            return redirect(url_for("family_suggestions"))

        # the reviewer can uncheck a member, so re-read the selection rather
        # than trusting the proposal that produced the form
        products = (
            Product.query
            .filter(Product.id.in_(product_ids))
            .filter(Product.family_id.is_(None))
            .all()
            if product_ids else []
        )

        if len(products) < 2:
            flash("لازم تختار منتجين على الأقل للمجموعة", "warning")
            return redirect(url_for("family_suggestions"))

        family = create_family(name, products)
        db.session.commit()

        log_activity(
            current_user.id,
            "CREATE_FAMILY",
            f"مجموعة جديدة: {family.name} ({len(products)} منتج)",
        )
        flash(f"تم إنشاء مجموعة «{family.name}» بـ {len(products)} منتج", "success")

        return redirect(url_for("family_suggestions"))

    @app.route("/families/suggestions/dismiss", methods=["POST"])
    @login_required
    @manager_required
    def dismiss_family_suggestion():
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        key = request.form.get("key", "").strip()

        if not key:
            flash("الاقتراح غير معروف", "danger")
            return redirect(url_for("family_suggestions"))

        dismiss_suggestion(key)
        db.session.commit()

        flash("تم تجاهل الاقتراح — مش رح يرجع يظهر", "info")

        return redirect(url_for("family_suggestions"))

    @app.route("/families")
    @login_required
    def family_list():
        families = (
            ProductFamily.query
            .options(
                joinedload(ProductFamily.category),
                joinedload(ProductFamily.variants).joinedload(Product.color),
                joinedload(ProductFamily.variants).joinedload(Product.locations),
            )
            .order_by(ProductFamily.name)
            .all()
        )

        return render_template(
            "family_list.html",
            families=families,
            pending=len(suggest_families()),
        )

    @app.route("/product/<int:product_id>/group-with-match", methods=["POST"])
    @login_required
    @manager_required
    def group_with_match(product_id):
        """Act on the banner offered on a product page.

        Joins the family the match already belongs to, or makes a new one from
        the products sharing the name. One click, at the moment the product is
        in front of the person — which is the only way grouping keeps up once
        the catalogue is in the thousands.
        """

        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)
        match = find_match(product)

        if match is None:
            flash("ما في منتج تاني بنفس الاسم", "warning")
            return redirect(url_for("product_details", product_id=product.id))

        if match["family"] is not None:
            family = link_product(product, match["family"])
            message = f"تم ضم «{product.name}» لمجموعة «{family.name}»"
        else:
            family = create_family(product.name, [product] + match["siblings"])
            message = (
                f"تم إنشاء مجموعة «{family.name}» "
                f"بـ {len(match['siblings']) + 1} منتج"
            )

        db.session.commit()

        log_activity(current_user.id, "LINK_FAMILY", message)
        flash(message, "success")

        return redirect(url_for("product_details", product_id=product.id))

    @app.route("/product/<int:product_id>/dismiss-match", methods=["POST"])
    @login_required
    @manager_required
    def dismiss_match(product_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)
        key = product.normalized_name

        if key:
            dismiss_suggestion(key)
            db.session.commit()

        flash("تمام — مش رح نسأل عن هاد الاسم مرة تانية", "info")

        return redirect(url_for("product_details", product_id=product.id))

    @app.route("/family/<int:family_id>/rename", methods=["POST"])
    @login_required
    @manager_required
    def rename_family_route(family_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        family = ProductFamily.query.get_or_404(family_id)
        old_name = family.name

        try:
            rename_family(family, request.form.get("name", ""))
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("family_details", family_id=family.id))

        db.session.commit()

        log_activity(
            current_user.id,
            "RENAME_FAMILY",
            f"تغيير اسم المجموعة من {old_name} إلى {family.name}",
        )
        flash("تم تغيير الاسم", "success")

        return redirect(url_for("family_details", family_id=family.id))

    @app.route("/family/<int:family_id>")
    @login_required
    def family_details(family_id):
        family = (
            ProductFamily.query
            .options(
                joinedload(ProductFamily.category),
                joinedload(ProductFamily.variants).joinedload(Product.color),
                joinedload(ProductFamily.variants).joinedload(Product.secondary_color),
                joinedload(ProductFamily.variants).joinedload(Product.size_data),
                joinedload(ProductFamily.variants).joinedload(Product.neck_size),
                joinedload(ProductFamily.variants)
                .joinedload(Product.locations)
                .joinedload(InventoryLocation.warehouse),
            )
            .filter_by(id=family_id)
            .first_or_404()
        )

        # a colour first, then a size, is the order people ask in
        variants = sorted(
            family.variants,
            key=lambda v: (
                v.color.name if v.color else "￿",
                v.neck_size.name if v.neck_size else "",
            ),
        )

        return render_template(
            "family_details.html",
            family=family,
            variants=variants,
        )

    @app.route("/product/<int:product_id>/unlink-family", methods=["POST"])
    @login_required
    @manager_required
    def unlink_product_family(product_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)

        if product.family_id is None:
            flash("المنتج مش ضمن مجموعة", "warning")
            return redirect(url_for("product_details", product_id=product.id))

        name = product.family.name
        unlink_product(product)
        db.session.commit()

        log_activity(
            current_user.id,
            "UNLINK_FAMILY",
            f"فك {product.name} من مجموعة {name}",
        )
        flash(f"تم فك «{product.name}» من مجموعة «{name}»", "success")

        return redirect(url_for("product_details", product_id=product.id))

    @app.route("/product/<int:product_id>/link-family", methods=["POST"])
    @login_required
    @manager_required
    def link_product_family(product_id):
        if not ensure_system_ready():
            return redirect(url_for("dashboard"))

        product = Product.query.get_or_404(product_id)
        family_id = request.form.get("family_id", type=int)

        if not family_id:
            flash("اختار مجموعة", "warning")
            return redirect(url_for("product_details", product_id=product.id))

        family = ProductFamily.query.get_or_404(family_id)

        link_product(product, family)
        db.session.commit()

        log_activity(
            current_user.id,
            "LINK_FAMILY",
            f"ربط {product.name} بمجموعة {family.name}",
        )
        flash(f"تم ربط «{product.name}» بمجموعة «{family.name}»", "success")

        return redirect(url_for("product_details", product_id=product.id))
