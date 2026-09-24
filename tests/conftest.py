# -*- coding: utf-8 -*-
"""Shared test fixtures.

Everything runs against a separate database (`<your db>_test`) built by the
real migrations, so the tests exercise the same indexes and CHECK constraints
production has — those live in migrations, not in the models, and a SQLite
stand-in would silently skip them.

Each test runs inside a transaction that is rolled back afterwards, so tests
never see each other's rows and the file can be run in any order.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine, text
from urllib.parse import urlparse, urlunparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def _test_database_url():
    url = urlparse(config.DATABASE_URL)
    return urlunparse(url._replace(path=url.path + "_test"))


TEST_DATABASE_URL = _test_database_url()

# Guard rail: if anything ever points these tests at the real database they
# must refuse to run rather than truncate production inventory.
if not TEST_DATABASE_URL.rstrip("/").endswith("_test"):
    raise RuntimeError(
        "اختبارات لازم تشتغل على قاعدة تنتهي بـ _test — توقفت لحماية بيانات الإنتاج"
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["STORAGE_BACKEND"] = "local"
config.DATABASE_URL = TEST_DATABASE_URL


def _ensure_database_exists():
    url = urlparse(TEST_DATABASE_URL)
    name = url.path.lstrip("/")
    admin = urlunparse(url._replace(path="/postgres"))

    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("select 1 from pg_database where datname = :n"), {"n": name}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()


@pytest.fixture(scope="session")
def app():
    """The real application, wired to the test database and migrated."""

    _ensure_database_exists()

    from app import app as flask_app
    from flask_migrate import upgrade

    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI=TEST_DATABASE_URL,
        RATELIMIT_ENABLED=False,
    )

    with flask_app.app_context():
        from models import db

        # Rebuild from scratch so a half-migrated leftover can't skew results.
        # The whole schema goes, not just the tables the models know about:
        # db.drop_all() leaves behind any table whose model was removed, and a
        # foreign key from that orphan then blocks dropping the tables it
        # points at. Safe only because of the _test guard above.
        db.session.execute(text("DROP SCHEMA public CASCADE"))
        db.session.execute(text("CREATE SCHEMA public"))
        db.session.commit()

        upgrade()

    yield flask_app


@pytest.fixture()
def db_session(app):
    """A clean database for every test.

    Nesting each test in a transaction and rolling it back is the usual trick,
    but the routes under test call `db.session.commit()` themselves, and
    Flask-SQLAlchemy hands them a session bound to the engine rather than to
    the test's connection — so the writes escape the wrapper and leak into the
    next test. Truncating afterwards is blunt, but at this size it costs
    milliseconds and it is impossible to get wrong.
    """

    from models import db

    with app.app_context():
        yield db.session

        db.session.rollback()
        db.session.remove()

        tables = [
            f'"{table.name}"'
            for table in reversed(db.metadata.sorted_tables)
        ]
        if tables:
            db.session.execute(
                text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )
            db.session.commit()
        db.session.remove()


@pytest.fixture()
def client(app, db_session):
    return app.test_client()


# ---------------------------------------------------------------- factories

@pytest.fixture()
def make_user(db_session):
    from models import User

    def _make(username="tester", role="ADMIN", password="pw-for-tests"):
        user = User(username=username, role=role)
        user.set_password(password)
        db_session.add(user)
        db_session.flush()
        return user

    return _make


@pytest.fixture()
def make_product(db_session):
    from models import Product, Color, Size, Category, SIZE_KIND_CAPACITY
    from utils.search_text import refresh_search_text

    def _make(name="منتج اختبار", minimum_stock=10, **kwargs):
        color = db_session.query(Color).first()
        if color is None:
            color = Color(name="أبيض اختبار", hex_code="#FFFFFF")
            db_session.add(color)
            db_session.flush()

        size = db_session.query(Size).first()
        if size is None:
            size = Size(name="500 مل اختبار", kind=SIZE_KIND_CAPACITY)
            db_session.add(size)
            db_session.flush()

        category = db_session.query(Category).first()
        if category is None:
            category = Category(name="تصنيف اختبار", sort_order=1)
            db_session.add(category)
            db_session.flush()

        product = Product(
            name=name,
            color_id=kwargs.get("color_id", color.id),
            size_id=kwargs.get("size_id", size.id),
            category_id=kwargs.get("category_id", category.id),
            minimum_stock=minimum_stock,
        )
        db_session.add(product)
        db_session.flush()

        # every route that creates a product does this, so a fixture that
        # skips it builds rows the application never produces — search and
        # grouping both read the derived columns
        refresh_search_text(product)
        db_session.flush()

        return product

    return _make


@pytest.fixture()
def make_location(db_session):
    from models import InventoryLocation, Warehouse

    def _make(product, quantity=0, warehouse_name="مستودع اختبار", location="A1"):
        warehouse = (
            db_session.query(Warehouse).filter_by(name=warehouse_name).first()
        )
        if warehouse is None:
            warehouse = Warehouse(name=warehouse_name)
            db_session.add(warehouse)
            db_session.flush()

        row = InventoryLocation(
            product_id=product.id,
            warehouse_id=warehouse.id,
            location=location,
            quantity=quantity,
        )
        db_session.add(row)
        db_session.flush()
        return row

    return _make


@pytest.fixture()
def login(client):
    """Put a user in the session without going through the password form."""

    def _login(user):
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        return client

    return _login
