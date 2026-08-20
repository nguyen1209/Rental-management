from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()
PRODUCT_SIZE_VALUES = ('XS', 'S', 'M', 'L', 'XL', 'XXL')

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
    id_card = db.Column(db.String(20))
    notes = db.Column(db.Text)
    password_hash = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    rentals = db.relationship('Rental', backref='customer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.String(20), nullable=False, default='unisex')
    sizes = db.Column(db.String(100))
    variants = db.Column(db.Text)
    description = db.Column(db.Text)
    price_per_day = db.Column(db.Float, nullable=False)
    deposit = db.Column(db.Float, default=0)
    quantity = db.Column(db.Integer, default=1)
    available_quantity = db.Column(db.Integer, default=1)
    image_url = db.Column(db.String(200))
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def size_list(self):
        if self.variant_list:
            variant_sizes = [item.get('size') for item in self.variant_list if item.get('size')]
            if variant_sizes:
                return list(dict.fromkeys(variant_sizes))
        return [size for size in (self.sizes or '').strip('|').split('|') if size]

    @property
    def variant_list(self):
        try:
            values = json.loads(self.variants or '[]')
            return values if isinstance(values, list) else []
        except (TypeError, ValueError):
            return []

    @property
    def gender_list(self):
        if self.variant_list:
            return list(dict.fromkeys(item['gender'] for item in self.variant_list))
        return [self.gender or 'unisex']

    @property
    def selectable_variants(self):
        sized = [item for item in self.variant_list if item.get('size')]
        if sized:
            return [{'gender': item['gender'], 'size': item['size'],
                     'available': item['available'], 'shared': False} for item in sized]
        options = []
        for item in self.gender_inventory:
            for size in PRODUCT_SIZE_VALUES:
                options.append({'gender': item['gender'], 'size': size,
                                'available': item['available'], 'shared': True})
        return options

    @property
    def size_inventory_groups(self):
        groups = {}
        for item in self.variant_list:
            gender = item.get('gender') or 'unisex'
            group = groups.setdefault(gender, {'gender': gender, 'sizes': {}})
            size = item.get('size') or 'M'
            current = group['sizes'].setdefault(size, {'quantity': 0, 'available': 0})
            current['quantity'] += item.get('quantity', 0)
            current['available'] += item.get('available', 0)
        return list(groups.values())

    @property
    def gender_inventory(self):
        grouped = {}
        for item in self.variant_list:
            value = grouped.setdefault(item['gender'], {'gender': item['gender'],
                                                        'quantity': 0, 'available': 0})
            value['quantity'] += item['quantity']
            value['available'] += item['available']
        return list(grouped.values())

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    children = db.relationship('Category', backref=db.backref('parent', remote_side=[id]),
                               lazy=True, cascade='all, delete-orphan', single_parent=True)

class Rental(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rental_code = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    rental_date = db.Column(db.DateTime, default=datetime.utcnow)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    actual_return_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='rented')
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Float, default=0)
    adjustment_amount = db.Column(db.Float, default=0)
    adjustment_note = db.Column(db.Text)
    payment_method = db.Column(db.String(20), default='cash')
    payment_status = db.Column(db.String(30), default='unpaid')
    paid_at = db.Column(db.DateTime)
    payment_receipt_url = db.Column(db.String(300))
    payment_submitted_at = db.Column(db.DateTime)
    
    details = db.relationship('RentalDetail', backref='rental', cascade='all, delete-orphan')

class RentalDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rental_id = db.Column(db.Integer, db.ForeignKey('rental.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price_per_day = db.Column(db.Float, nullable=False)
    days = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    selected_size = db.Column(db.String(10))
    selected_gender = db.Column(db.String(20))
    
    product = db.relationship('Product', backref='rental_details')
