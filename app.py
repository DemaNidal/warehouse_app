from flask import (
    Flask,
    render_template,
    send_from_directory
)

from models import db, Warehouse, User
from flask_login import LoginManager
from routes.auth_routes import (
    register_auth_routes
)
from datetime import timedelta
from routes.product_routes import register_product_routes
from routes.color_routes import register_color_routes
from routes.setup_routes import register_setup_routes
from routes.location_routes import register_location_routes
from routes.search_routes import register_search_routes
from routes.dashboard_routes import register_dashboard_routes
from routes.transaction_routes import (
    register_transaction_routes
)
from routes.transfer_routes import register_transfer_routes

app = Flask(__name__)

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.secret_key = "f8b7e3d4a9c1e2f6b8a4d7e9c3f1a5b2"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///warehouse.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "uploads"

db.init_app(app)

with app.app_context():
    db.create_all()



@login_manager.user_loader
def load_user(user_id):

    return User.query.get(
        int(user_id)
    )


@app.route("/")
def home():

    warehouses = Warehouse.query.order_by(
        Warehouse.name
    ).all()

    return render_template(
        "index.html",
        warehouses=warehouses
    )


@app.route("/uploads/<filename>")
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


register_product_routes(app)
register_color_routes(app)
register_setup_routes(app)
register_location_routes(app)
register_search_routes(app)
register_dashboard_routes(app)
register_transaction_routes(app)
register_transfer_routes(app)
register_auth_routes(app)
if __name__ == "__main__":
    app.run(host="0.0.0.0")