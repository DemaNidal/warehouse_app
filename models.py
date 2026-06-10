from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

db = SQLAlchemy()
TRANSACTION_TYPES = [
    "IN",
    "OUT",
    "TRANSFER",
    "ADJUSTMENT"
]
TRANSACTION_LABELS = {
    "IN": "إدخال",
    "OUT": "إخراج",
    "TRANSFER": "تحويل",
    "ADJUSTMENT": "تسوية"
}

class Color(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )


class Product(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(255),
        nullable=False
    )

    size = db.Column(
        db.String(100)
    )

    image = db.Column(
        db.String(255)
    )

    color_id = db.Column(
        db.Integer,
        db.ForeignKey("color.id")
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now(),
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False
    )

    color = db.relationship("Color")

    locations = db.relationship(
        "InventoryLocation",
        back_populates="product",
        lazy=True
    )

    transactions = db.relationship(
        "InventoryTransaction",
        back_populates="product",
        lazy=True
    )

class Warehouse(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    locations = db.relationship(
        "InventoryLocation",
        back_populates="warehouse",
        lazy=True
    )


class InventoryLocation(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    warehouse_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse.id"),
        nullable=False
    )

    location = db.Column(
        db.String(255),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    product = db.relationship(
        "Product",
        back_populates="locations"
    )

    warehouse = db.relationship(
        "Warehouse",
        back_populates="locations"
    )

    transactions = db.relationship(
        "InventoryTransaction",
        foreign_keys="InventoryTransaction.location_id",
        back_populates="location",
        lazy=True
    )


class InventoryTransaction(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    location_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_location.id"),
        nullable=False
    )

    destination_location_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_location.id")
    )

    transaction_type = db.Column(
        db.String(20),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    notes = db.Column(
        db.String(255)
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now(),
        nullable=False
    )

    product = db.relationship(
        "Product",
        back_populates="transactions"
    )

    location = db.relationship(
        "InventoryLocation",
        foreign_keys=[location_id],
        back_populates="transactions"
    )

    destination_location = db.relationship(
        "InventoryLocation",
        foreign_keys=[destination_location_id]
    )


class User( UserMixin, db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="EMPLOYEE"
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    def set_password(
        self,
        password
    ):
        self.password_hash = generate_password_hash(
            password
        )

    def check_password(
        self,
        password
    ):
        return check_password_hash(
            self.password_hash,
            password
        )