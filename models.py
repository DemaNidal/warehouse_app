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
SIZE_KIND_CAPACITY = "CAPACITY"   # how much it holds: 500 مل، 1 لتر، 48.7 غم
SIZE_KIND_NECK = "NECK"           # what it screws onto: 28/410، 38، 89
SIZE_KINDS = [SIZE_KIND_CAPACITY, SIZE_KIND_NECK]
SIZE_KIND_LABELS = {
    SIZE_KIND_CAPACITY: "السعة",
    SIZE_KIND_NECK: "مقاس الرقبة"
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

    hex_code = db.Column(
        db.String(7),
        nullable=True
    )

    products = db.relationship(
        "Product",
        backref="color_data",
        lazy=True,
        viewonly=True,
        foreign_keys="Product.color_id"
    )

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(150),
        unique=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.now,
        nullable=False
    )

class Size(db.Model):
    """A measurement a product can carry.

    Two different things used to share this table with no way to tell them
    apart: how much a container holds ("500 مل") and what thread it screws
    onto ("28/410"). A bottle has both, a cap only has a neck — so `kind`
    says which one a row is, and Product points at it through two separate
    columns: `size_id` for the capacity, `neck_size_id` for the neck.
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    kind = db.Column(
        db.String(20),
        nullable=False,
        default=SIZE_KIND_CAPACITY,
        server_default=SIZE_KIND_CAPACITY
    )

    products = db.relationship(
        "Product",
        backref="size_data",
        lazy=True,
        foreign_keys="Product.size_id"
    )

    neck_products = db.relationship(
        "Product",
        lazy=True,
        viewonly=True,
        foreign_keys="Product.neck_size_id"
    )


class Category(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    slug = db.Column(
        db.String(120),
        unique=True,
        nullable=True
    )

    icon = db.Column(
        db.String(50),
        nullable=True
    )

    sort_order = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.now,
        nullable=False
    )

    products = db.relationship(
        "Product",
        back_populates="category",
        lazy=True
    )


class ProductFamily(db.Model):
    """One product sold in several colours or sizes.

    A family is a decision, not a guess: rows land here only because someone
    said "these are the same item". Products with no family keep behaving
    exactly as they always have, so the catalogue works whether or not anyone
    ever groups anything.

    Stock stays on the Product — the physical count is per colour, and moving
    it here would mean rewriting every location and transaction for no gain.
    """

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255), nullable=False)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("category.id"),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now(),
        nullable=False
    )

    category = db.relationship("Category")

    variants = db.relationship(
        "Product",
        back_populates="family",
        lazy="selectin"
    )

    @property
    def total_quantity(self):
        return sum(variant.total_quantity for variant in self.variants)

    @property
    def colors(self):
        """The distinct colours across the variants, in a stable order."""
        seen = {}
        for variant in self.variants:
            if variant.color and variant.color.id not in seen:
                seen[variant.color.id] = variant.color
        return list(seen.values())

    @property
    def stock_status(self):
        """The worst status among the variants.

        A family showing "متوفر" while one of its colours has run out would
        hide exactly the thing worth acting on.
        """
        statuses = [variant.stock_status for variant in self.variants]

        if not statuses or STOCK_CRITICAL in statuses:
            return STOCK_CRITICAL

        if STOCK_LOW in statuses:
            return STOCK_LOW

        return STOCK_NORMAL


class FamilySuggestionDismissal(db.Model):
    """A grouping suggestion that was looked at and rejected.

    Suggestions are recomputed from the catalogue every time the screen opens,
    so without a record of the rejections the same answered question comes back
    forever. Keyed by the normalised name the suggestion was built from.
    """

    id = db.Column(db.Integer, primary_key=True)

    normalized_name = db.Column(
        db.String(255),
        unique=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now(),
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

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("category.id"),
        nullable=True
    )

    # Nullable on purpose: an ungrouped product is the normal case, not an
    # unfinished one.
    family_id = db.Column(
        db.Integer,
        db.ForeignKey("product_family.id"),
        nullable=True
    )

    size_id = db.Column(
        db.Integer,
        db.ForeignKey("size.id")
    )

    neck_size_id = db.Column(
        db.Integer,
        db.ForeignKey("size.id"),
        nullable=True
    )

    image = db.Column(
        db.String(255)
    )

    # The product name with spelling folded (أ/إ/آ→ا, ة→ه, ى→ي). Indexed, so
    # "is there another product with this name" is one lookup rather than a
    # scan of the catalogue — which is what grouping suggestions ask on every
    # product page.
    normalized_name = db.Column(
        db.String(255),
        nullable=True,
        index=True
    )

    # Normalised text built from the name, colours, category and measurements.
    # Maintained by utils.search_text; indexed with pg_trgm so partial matches
    # stay fast as the catalogue grows past a few thousand rows.
    search_text = db.Column(
        db.Text,
        nullable=True
    )

    color_id = db.Column(
        db.Integer,
        db.ForeignKey("color.id")
    )

    secondary_color_id = db.Column(
        db.Integer,
        db.ForeignKey("color.id"),
        nullable=True
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

    color = db.relationship("Color", foreign_keys=[color_id])
    secondary_color = db.relationship("Color", foreign_keys=[secondary_color_id])

    category = db.relationship(
        "Category",
        back_populates="products"
    )

    family = db.relationship(
        "ProductFamily",
        back_populates="variants"
    )

    neck_size = db.relationship(
        "Size",
        foreign_keys=[neck_size_id]
    )

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
        nullable=True
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

    quantity_before = db.Column(
        db.Integer,
        nullable=True
    )

    quantity_after = db.Column(
        db.Integer,
        nullable=True
    )

    quantity_expression = db.Column(
        db.String(255),
        nullable=True
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

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customer.id")
    )
    customer = db.relationship(
        "Customer"
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
    target_url = db.Column(
        db.String(255),
        nullable=True
    )

class StockRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(db.Integer, db.ForeignKey("product.id"))
    location_id = db.Column(db.Integer, db.ForeignKey("inventory_location.id"))

    quantity = db.Column(db.Integer)
    quantity_expression = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.String(255))

    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))

    status = db.Column(
        db.String(20),
        default="PENDING",
        nullable=False
    )

    requested_by = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    approved_by = db.Column(
        db.Integer,
        db.ForeignKey("user.id")
    )

    approved_at = db.Column(db.DateTime)

    rejected_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.now)

    # ✅ IMPORTANT RELATIONSHIPS
    product = db.relationship("Product")
    location = db.relationship("InventoryLocation")
    customer = db.relationship("Customer")
    requester = db.relationship(
        "User",
        foreign_keys=[requested_by]
    )
    approver = db.relationship(
        "User",
        foreign_keys=[approved_by]
    )