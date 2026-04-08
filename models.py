from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    fullname = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))
    id_card = db.Column(db.String(20))  # Số CMND/CCCD
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    rentals = db.relationship('Rental', backref='customer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    price_per_day = db.Column(db.Float, nullable=False)
    deposit = db.Column(db.Float, nullable=True, default=0)
    quantity = db.Column(db.Integer, default=1)
    available_quantity = db.Column(db.Integer, default=1)
    image_url = db.Column(db.String(200))
    status = db.Column(db.String(20), default='active')  # active, inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    rentals = db.relationship('Rental', backref='product', lazy=True)

class Rental(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rental_code = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    rental_date = db.Column(db.DateTime, default=datetime.utcnow)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    actual_return_date = db.Column(db.DateTime)
    price_per_day = db.Column(db.Float, nullable=False)
    deposit_amount = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    deposit_returned = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')  # pending, rented, returned, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def calculate_total_price(self):
        days = (self.end_date - self.start_date).days
        return self.price_per_day * days * self.quantity