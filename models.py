from datetime import datetime

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
STOCK_NORMAL = "NORMAL"
STOCK_LOW = "LOW"
STOCK_CRITICAL = "CRITICAL"

class Color(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

class Size(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    products = db.relationship(
        "Product",
        backref="size_data",
        lazy=True
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

    size_id = db.Column(
        db.Integer,
        db.ForeignKey("size.id")
    )

    image = db.Column(
        db.String(255)
    )

    color_id = db.Column(
        db.Integer,
        db.ForeignKey("color.id")
    )
    minimum_stock = db.Column(
        db.Integer,
        nullable=False,
        default=10
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now(),
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.now,
        onupdate=datetime.now,
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
    @property
    def total_quantity(self):
        return sum(location.quantity for location in self.locations)
    @property
    def stock_status(self):

        qty = self.total_quantity

        if qty == 0:
            return STOCK_CRITICAL

        if qty <= self.minimum_stock:
            return STOCK_LOW

        return STOCK_NORMAL

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

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id")
    )
    user = db.relationship(
        "User"
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
        default=datetime.now
    )
    is_active_user = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )
    notifications = db.relationship(
        "Notification",
        back_populates="user",
        lazy=True
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
    
class ActivityLog(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    action = db.Column(
        db.String(255),
        nullable=False
    )

    description = db.Column(
        db.String(500)
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.now,
        nullable=False
    )

    user = db.relationship(
        "User"
    )

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    type = db.Column(db.String(20), nullable=False)
    # STOCK_LOW / STOCK_CRITICAL

    is_read = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    user = db.relationship("User", back_populates="notifications")
    product = db.relationship("Product")