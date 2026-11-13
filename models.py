from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from services.inventory_logic import (
    calculate_safety_stock,
    calculate_min_stock,
    calculate_max_stock,
    get_inventory_status,
    get_expiry_status,
)

db = SQLAlchemy()

class Category(db.Model):
    """Pharmaceutical categories (e.g., Antibiotics, Analgesics, Cardiovascular)."""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    medicines = db.relationship('Medicine', backref='category', lazy=True)

    def __repr__(self):
        return f"<Category {self.name}>"


class Medicine(db.Model):
    """Medicine master record including therapeutic info and inventory planning parameters."""
    __tablename__ = 'medicines'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(120), nullable=False)
    generic_name = db.Column(db.String(120), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    dosage_form = db.Column(db.String(50), nullable=False, default='Tablet')  # Tablet, Syrup, Injection, etc.
    strength = db.Column(db.String(50), nullable=False)                      # e.g., 500mg, 10mg/5ml
    unit = db.Column(db.String(50), nullable=False, default='Tablets')        # Tablets, Bottles, Ampoules, Strips

    # Pharmacy Inventory Parameters
    avg_daily_consumption = db.Column(db.Float, nullable=False, default=10.0) # Average Daily Consumption (ADC)
    lead_time_days = db.Column(db.Integer, nullable=False, default=7)         # Supplier Lead Time (LT) in days
    safety_stock_days = db.Column(db.Integer, nullable=False, default=5)      # Safety Stock buffer period in days
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    batches = db.relationship('Batch', backref='medicine', cascade='all, delete-orphan', lazy=True)
    transactions = db.relationship('StockTransaction', backref='medicine', cascade='all, delete-orphan', lazy=True)

    @property
    def total_stock(self):
        """Current total available stock across all active non-expired batches."""
        today = date.today()
        return sum(b.quantity for b in self.batches if b.quantity > 0 and b.expiry_date > today)

    @property
    def total_stock_all_batches(self):
        """Total stock including expired units (for audit/quarantine purposes)."""
        return sum(b.quantity for b in self.batches)

    @property
    def safety_stock(self):
        """Buffer stock required to absorb supplier delays or sudden demand surges."""
        return calculate_safety_stock(self.avg_daily_consumption, self.safety_stock_days)

    @property
    def min_stock(self):
        """Minimum Stock Level (Reorder Point): Trigger point to place a new purchase order."""
        return calculate_min_stock(self.avg_daily_consumption, self.lead_time_days, self.safety_stock)

    @property
    def max_stock(self):
        """Maximum Stock Level: Ceiling to prevent capital lockup and expiry spoilage."""
        return calculate_max_stock(self.min_stock, self.avg_daily_consumption)

    @property
    def stock_status(self):
        """Returns the current inventory health status (e.g., NORMAL, LOW_STOCK, OUT_OF_STOCK)."""
        return get_inventory_status(self.total_stock, self.min_stock, self.max_stock)

    @property
    def earliest_expiring_batch(self):
        """Returns the batch with the earliest expiration date that still has stock (FEFO priority)."""
        active_batches = [b for b in self.batches if b.quantity > 0]
        if not active_batches:
            return None
        return min(active_batches, key=lambda b: b.expiry_date)

    def __repr__(self):
        return f"<Medicine {self.brand_name} ({self.generic_name})>"


class Batch(db.Model):
    """Specific manufacturing batch/lot for a medicine, tracking expiry date and cost."""
    __tablename__ = 'batches'

    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'), nullable=False)
    batch_number = db.Column(db.String(60), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    initial_quantity = db.Column(db.Integer, nullable=False, default=0)
    expiry_date = db.Column(db.Date, nullable=False)
    received_date = db.Column(db.Date, nullable=False, default=date.today)
    purchase_price = db.Column(db.Float, nullable=False, default=0.0)  # Purchase cost per unit
    selling_price = db.Column(db.Float, nullable=False, default=0.0)   # Selling price per unit
    supplier = db.Column(db.String(120), nullable=True)

    transactions = db.relationship('StockTransaction', backref='batch', lazy=True)

    @property
    def days_until_expiry(self):
        """Number of calendar days remaining until this batch reaches expiry."""
        today = date.today()
        return (self.expiry_date - today).days

    @property
    def expiry_status(self):
        """Returns EXPIRED, CRITICAL (<30 days), WARNING (<90 days), or GOOD (>90 days)."""
        status, _ = get_expiry_status(self.expiry_date)
        return status

    def __repr__(self):
        return f"<Batch {self.batch_number} - Med ID: {self.medicine_id}>"


class StockTransaction(db.Model):
    """Audit log recording every stock movement (dispensing, restocking, or disposal)."""
    __tablename__ = 'stock_transactions'

    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=True)
    transaction_type = db.Column(db.String(30), nullable=False)  # DISPENSE, RESTOCK, ADJUSTMENT, DISPOSE_EXPIRED
    quantity = db.Column(db.Integer, nullable=False)
    reference_no = db.Column(db.String(80), nullable=True)       # e.g., Prescription #, Invoice #
    notes = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Transaction {self.transaction_type} {self.quantity} of Med ID: {self.medicine_id}>"
