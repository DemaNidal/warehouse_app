from models import db, Warehouse
from flask_login import login_required
from utils.permissions import admin_required

def register_setup_routes(app):

    @app.route("/setup")
    @login_required
    @admin_required
    def setup():

        warehouses = [
            "الساحة",
            "الطابق الثالث",
            "الطابق الثاني",
            "الطابق الاول",
            "البيارة",
            "الدحدوح",
            "معرض نابلس"
        ]

        for name in warehouses:

            exists = Warehouse.query.filter_by(
                name=name
            ).first()

            if not exists:

                db.session.add(
                    Warehouse(name=name)
                )

        db.session.commit()

        return "Warehouses Created"