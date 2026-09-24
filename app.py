import os
import shutil
import logging
from logging.handlers import RotatingFileHandler

os.makedirs("logs", exist_ok=True)

_log_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

_file_handler = RotatingFileHandler(
    "logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(_log_formatter)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)

logging.basicConfig(
    level=logging.WARNING,
    handlers=[_console_handler, _file_handler]
)
logging.getLogger("werkzeug").setLevel(logging.INFO)

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for
)

from models import db, Warehouse, User, Product
from flask_login import LoginManager, login_required
from routes.auth_routes import (
    register_auth_routes
)
from datetime import datetime, timedelta
from routes.product_routes import register_product_routes
from routes.color_routes import register_color_routes
from routes.category_routes import register_category_routes
from routes.requests_routes import register_requests_routes
from routes.setup_routes import register_setup_routes
from routes.location_routes import register_location_routes
from routes.search_routes import register_search_routes
from routes.dashboard_routes import register_dashboard_routes
from routes.transaction_routes import (
    register_transaction_routes
)
from utils.context_processors import register_context_processors
from utils.storage import init_storage
from routes.user_routes import register_user_routes
from routes.transfer_routes import register_transfer_routes
from routes.size_routes import register_size_routes
from routes.activity_routes import register_activity_routes
from routes.backup_routes import (
    register_backup_routes
)
from routes.notifications_routes import register_notifications_routes
from routes.settings_routes import register_settings_routes
from routes.create_admin_route import register_create_admin_route
from routes.customer_routes import register_customer_routes
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

# Without a ceiling Flask buffers the whole request body in memory, so one
# oversized upload can take the process down. Photos straight off a phone are
# a few MB; 25 is generous and still bounded.
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Session hardening. SECURE must stay off until the app is actually served over
# HTTPS — turning it on over plain HTTP makes the browser drop the cookie and
# nobody can log in. Flip SESSION_COOKIE_SECURE=true in .env at that point.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"
)

# Behind Caddy every request arrives from the proxy, so without this the rate
# limiter sees one client for the whole internet and Flask builds http:// links
# on an https:// site. Opt-in, because trusting these headers when the app is
# NOT behind a proxy would let anyone forge their own address.
if os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() == "true":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

init_storage(app)

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


@app.errorhandler(413)
def payload_too_large(error):

    # MAX_CONTENT_LENGTH rejects the request before any view runs, so say what
    # happened instead of showing a bare server error.
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    flash(f"الملف كبير جداً — الحد الأقصى {limit_mb} ميجابايت", "danger")

    return redirect(request.referrer or url_for("home")), 302


@app.errorhandler(500)
def server_error(error):

    db.session.rollback()
    app.logger.exception("Unhandled 500 error on %s %s", request.method, request.path)

    return render_template(
        "500.html"
    ), 500


@app.after_request
def add_no_cache_headers(response):

    # Prevent the browser from serving cached/bfcache copies of
    # authenticated pages after logout (back-button data exposure).
    if not request.path.startswith("/static/") and not request.path.startswith("/uploads/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"

    return response

@app.route("/")
@login_required
def home():

    warehouses = Warehouse.query.order_by(
        Warehouse.name
    ).all()

    product_count = Product.query.count()

    greeting = "صباح الخير" if datetime.now().hour < 12 else "مساء الخير"

    return render_template(
        "index.html",
        warehouses=warehouses,
        product_count=product_count,
        greeting=greeting
    )


# Uploaded filenames are UUID-prefixed, so a given name always points at the
# same bytes — replacing a product image writes a new name. That makes them
# safe to cache hard, which matters here: the product list renders 20 images
# and Flask's default (no-cache) makes the browser revalidate every one on
# every page load, tying up a waitress thread each time.
UPLOAD_CACHE_SECONDS = 60 * 60 * 24 * 30  # 30 days


@app.route("/uploads/<filename>")
def uploaded_file(filename):

    response = send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        max_age=UPLOAD_CACHE_SECONDS
    )

    # send_from_directory sets max-age; mark it immutable too so browsers skip
    # the revalidation round-trip entirely instead of sending If-None-Match.
    response.headers["Cache-Control"] = (
        f"public, max-age={UPLOAD_CACHE_SECONDS}, immutable"
    )

    return response



register_product_routes(app)
register_color_routes(app)
register_category_routes(app)
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
register_create_admin_route(app)
register_customer_routes(app)


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