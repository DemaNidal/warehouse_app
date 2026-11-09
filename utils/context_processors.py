from flask_login import current_user

from models import Notification, StockRequest
from utils.clock import to_local
from utils.color_names import EMPTY_SWATCH, swatch


def register_context_processors(app):

    # Everything is stored in UTC (see utils/clock). Templates call
    # `.strftime` on these columns directly, so the conversion has to happen
    # before they do — a filter, applied at the point of display.
    @app.template_filter("local")
    def _local(value):
        return to_local(value)


    # Four templates had each chosen their own grey for a colour with no
    # code — #e2e8f0, #94A3B8, #ccc and #cccccc — so the same state drew
    # differently depending on which page you were on.
    @app.template_filter("swatch")
    def _swatch(hex_code):
        return swatch(hex_code)


    @app.context_processor
    def inject_swatch_default():
        return {"empty_swatch": EMPTY_SWATCH}


    @app.context_processor
    def inject_navbar_counts():

        if not current_user.is_authenticated:
            return {
                "unread_notifications": 0,
                "pending_requests_count": 0
            }

        unread_notifications = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()

        pending_requests_count = 0

        if current_user.role == "ADMIN":
            pending_requests_count = StockRequest.query.filter_by(
                status="PENDING"
            ).count()

        return {
            "unread_notifications": unread_notifications,
            "pending_requests_count": pending_requests_count
        }