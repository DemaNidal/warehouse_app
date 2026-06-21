from models import db, Notification, STOCK_LOW, STOCK_CRITICAL

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