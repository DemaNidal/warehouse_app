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

        # safety check (prevents re-seeding)
        if Warehouse.query.first():
            return "Setup already completed"

        # get existing names once
        existing = {
            w.name for w in Warehouse.query.filter(
                Warehouse.name.in_(warehouses)
            ).all()
        }

        # build only missing ones
        new_warehouses = [
            Warehouse(name=name)
            for name in warehouses
            if name not in existing
        ]

        db.session.add_all(new_warehouses)
        db.session.commit()

        return f"Inserted {len(new_warehouses)} warehouses"