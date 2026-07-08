import os
import shutil

from flask import (
    Flask,
    render_template,
    send_from_directory
)

from models import db, Warehouse, User
from flask_login import LoginManager, login_required
from routes.auth_routes import (
    register_auth_routes
)
from datetime import datetime, timedelta
from routes.product_routes import register_product_routes
from routes.color_routes import register_color_routes
from routes.requests_routes import register_requests_routes
from routes.setup_routes import register_setup_routes
from routes.location_routes import register_location_routes
from routes.search_routes import register_search_routes
from routes.dashboard_routes import register_dashboard_routes
from routes.transaction_routes import (
    register_transaction_routes
)
from utils.context_processors import register_context_processors
from routes.user_routes import register_user_routes
from routes.transfer_routes import register_transfer_routes
from routes.size_routes import register_size_routes
from routes.activity_routes import register_activity_routes
from routes.backup_routes import (
    register_backup_routes
)
from routes.notifications_routes import register_notifications_routes
from routes.settings_routes import register_settings_routes
from flask_wtf.csrf import CSRFProtect
import click
import config
from flask_migrate import Migrate
from extensions import limiter




csrf = CSRFProtect()
app = Flask(__name__)

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
if not config.SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable must be set")
app.secret_key = config.SECRET_KEY
csrf.init_app(app)
limiter.init_app(app)
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "uploads"

db.init_app(app)
migrate = Migrate(app, db)




@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )
    
@app.errorhandler(404)
def not_found(error):

    return render_template(
        "404.html"
    ), 404


@app.errorhandler(500)
def server_error(error):

    db.session.rollback()

    return render_template(
        "500.html"
    ), 500

@app.route("/")
@login_required
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
register_size_routes(app)
register_auth_routes(app)
register_user_routes(app)
register_activity_routes(app)
register_backup_routes(app)
register_notifications_routes(app)
register_context_processors(app)
register_requests_routes(app)
register_settings_routes(app)


@app.cli.command("create-admin")
def create_admin():
    """Create the initial ADMIN user (refuses if one already exists)."""

    existing_user = User.query.filter_by(role="ADMIN").first()

    if existing_user:
        click.echo(f"An ADMIN user already exists: {existing_user.username}")
        return

    username = click.prompt("Admin username")

    password = click.prompt(
        "Admin password",
        hide_input=True,
        confirmation_prompt=True
    )

    user = User(username=username, role="ADMIN")
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    click.echo(f"Admin user '{username}' created.")


if __name__ == "__main__":

    app.run(host="0.0.0.0")