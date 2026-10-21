# -*- coding: utf-8 -*-
"""Telling people the things they would otherwise have to go and look for."""

from flask import url_for

from models import db, Notification, STOCK_LOW, STOCK_CRITICAL, User

def generate_stock_notifications(product, users):

    if product.stock_status not in [STOCK_LOW, STOCK_CRITICAL]:
        return

    notif_type = product.stock_status

    for user in users:

        # prevent duplicates
        existing = Notification.query.filter_by(
            user_id=user.id,
            product_id=product.id,
            type=notif_type,
            is_read=False
        ).first()

        if existing:
            continue

        notification = Notification(
            user_id=user.id,
            product_id=product.id,
            type=notif_type
        )

        db.session.add(notification)

# ---------------------------------------------------------- stock requests
#
# None of this existed. A request was saved and the person who made it got a
# flash message; nobody else was told, so a manager only learned of it by
# opening the requests page on the off chance. Approving told nobody at all,
# although the notifications page has carried an "OUT_APPROVED" branch —
# icon, wording and all — the whole time, waiting for a notification that
# no code ever created. Rejecting was the only path that notified anyone,
# and in twenty-six requests it had never once been taken.


def notify_managers_of_request(stock_request):
    """Tell whoever can act on it that a request is waiting.

    Admins only. Approving and rejecting are both @admin_required, so a
    store manager cannot do anything with the news; alerting someone about
    a decision they are not allowed to make is noise. Nor the person who
    made the request, even when they are an admin themselves.
    """
    managers = User.query.filter(
        User.role == "ADMIN",
        User.id != stock_request.requested_by,
    ).all()

    for manager in managers:
        db.session.add(Notification(
            user_id=manager.id,
            product_id=stock_request.product_id,
            type="OUT_REQUESTED",
            is_read=False,
            target_url=url_for("stock_requests"),
        ))

    return len(managers)


def notify_requester(stock_request, approved):
    """Tell whoever asked what was decided.

    The requester may well be the person who decided — a manager approving
    their own request — and there is nothing to tell them in that case.
    """
    if stock_request.approved_by == stock_request.requested_by:
        return False

    db.session.add(Notification(
        user_id=stock_request.requested_by,
        product_id=stock_request.product_id,
        type="OUT_APPROVED" if approved else "OUT_REJECTED",
        is_read=False,
        target_url=url_for(
            "product_details", product_id=stock_request.product_id
        ),
    ))
    return True
