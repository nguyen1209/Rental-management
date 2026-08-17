from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.wsgi import FileWrapper
from datetime import datetime, timedelta
import calendar
import secrets
import os
import json
from urllib.parse import urlencode
from dotenv import load_dotenv
from sqlalchemy import func, desc, text, or_

from models import db, Admin, Customer, Product, Category, Rental, RentalDetail

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

app = Flask(__name__)

PRODUCT_GENDERS = {'male': 'Nam', 'female': 'Nữ', 'unisex': 'Unisex'}
PRODUCT_SIZES = ('XS', 'S', 'M', 'L', 'XL', 'XXL')

# Cấu hình
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///rental.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cấu hình upload
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['BANK_CODE'] = os.environ.get('BANK_CODE', '').strip().upper()
app.config['BANK_ACCOUNT'] = os.environ.get('BANK_ACCOUNT', '').strip()
app.config['BANK_ACCOUNT_NAME'] = os.environ.get('BANK_ACCOUNT_NAME', '').strip().upper()
app.config['PUBLIC_BASE_URL'] = os.environ.get(
    'PUBLIC_BASE_URL', 'https://trangphucbieudienphuonglan.io.vn').rstrip('/')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.context_processor
def inject_csrf_token():
    def csrf_token():
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['_csrf_token'] = token
        return token
    def bank_transfer(rental=None):
        info = {
            'bank_code': app.config['BANK_CODE'],
            'account': app.config['BANK_ACCOUNT'],
            'account_name': app.config['BANK_ACCOUNT_NAME'],
        }
        if rental and info['bank_code'] and info['account']:
            query = urlencode({
                'amount': int(rental.total_amount or 0),
                'addInfo': rental.rental_code,
                'accountName': info['account_name'],
            })
            info['qr_url'] = (f"https://img.vietqr.io/image/{info['bank_code']}-"
                              f"{info['account']}-compact2.png?{query}")
        return info
    return {'csrf_token': csrf_token, 'bank_transfer': bank_transfer,
            'product_genders': PRODUCT_GENDERS, 'product_sizes': PRODUCT_SIZES}

@app.before_request
def protect_post_requests():
    if request.method == 'POST':
        expected = session.get('_csrf_token', '')
        supplied = request.form.get('_csrf_token', '') or request.headers.get('X-CSRF-Token', '')
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, description='Yêu cầu không hợp lệ hoặc đã hết hạn. Vui lòng tải lại trang.')

@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return response

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def product_image_from_request(current_url=None):
    """Save a camera/gallery upload, falling back to an explicitly supplied URL."""
    file = request.files.get('camera_image') or request.files.get('image')
    if file and file.filename:
        if not allowed_file(file.filename) or not (file.mimetype or '').startswith('image/'):
            raise ValueError('Ảnh phải có định dạng PNG, JPG, JPEG, GIF hoặc WEBP.')
        extension = secure_filename(file.filename).rsplit('.', 1)[1].lower()
        filename = f"product_{secrets.token_hex(10)}.{extension}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return url_for('static', filename=f'uploads/{filename}')
    if request.form.get('remove_image') == '1':
        return None
    return request.form.get('image_url', '').strip() or current_url

DEFAULT_CATEGORIES = ['Quần áo', 'Phụ kiện', 'Đạo cụ']

def get_product_categories():
    managed = [category.name for category in Category.query.order_by(
        Category.parent_id.asc(), Category.sort_order.asc(), Category.name.asc()).all()]
    existing = [row[0].strip() for row in db.session.query(Product.category).distinct().all()
                if row[0] and row[0].strip()]
    result = DEFAULT_CATEGORIES + managed + existing
    return list(dict.fromkeys(result))

def category_from_form():
    category = request.form.get('category', '').strip()
    if category == '__other__':
        category = request.form.get('custom_category', '').strip()
    if not category:
        raise ValueError('Vui lòng chọn hoặc nhập danh mục sản phẩm!')
    if not Category.query.filter_by(name=category).first():
        db.session.add(Category(name=category))
    return category

def product_variants_from_form():
    genders = request.form.getlist('variant_gender[]')
    quantities = request.form.getlist('variant_quantity[]')
    if not genders or len(genders) != len(quantities):
        raise ValueError('Vui lòng nhập ít nhất một phân loại Nam/Nữ và số lượng!')
    variants = []
    seen = set()
    for gender, raw_quantity in zip(genders, quantities):
        gender = gender.strip().lower()
        if gender not in PRODUCT_GENDERS:
            raise ValueError('Phân loại không hợp lệ!')
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            raise ValueError('Số lượng của từng biến thể không hợp lệ!')
        if quantity < 0 or gender in seen:
            raise ValueError('Số lượng phải từ 0 và mỗi phân loại chỉ được nhập một lần!')
        seen.add(gender)
        variants.append({'gender': gender, 'size': '', 'quantity': quantity,
                         'available': quantity})
    if not any(item['quantity'] for item in variants):
        raise ValueError('Tổng số lượng sản phẩm phải lớn hơn 0!')
    return variants

def update_product_variants(product, submitted_variants):
    old = {}
    for item in product.variant_list:
        previous = old.setdefault(item['gender'], {'quantity': 0, 'available': 0})
        previous['quantity'] += item['quantity']
        previous['available'] += item['available']
    for item in submitted_variants:
        previous = old.get(item['gender'])
        rented = max(previous['quantity'] - previous['available'], 0) if previous else 0
        if item['quantity'] < rented:
            label = PRODUCT_GENDERS[item['gender']]
            raise ValueError(f'Không thể giảm {label} dưới {rented} món đang được thuê!')
        item['available'] = item['quantity'] - rented
    product.variants = json.dumps(submitted_variants, ensure_ascii=False)
    product.quantity = sum(item['quantity'] for item in submitted_variants)
    product.available_quantity = sum(item['available'] for item in submitted_variants)
    product.gender = 'unisex'
    product.sizes = '|' + '|'.join(PRODUCT_SIZES) + '|'

def find_variant(product, gender, size):
    return next((item for item in product.variant_list
                 if item['gender'] == gender and (not item.get('size') or item['size'] == size)), None)

def restore_detail_inventory(product, detail):
    variants = product.variant_list
    variant = next((item for item in variants if item['gender'] == detail.selected_gender
                    and (not item.get('size') or item['size'] == detail.selected_size)), None)
    if variant:
        variant['available'] = min(variant['quantity'], variant['available'] + detail.quantity)
        product.variants = json.dumps(variants, ensure_ascii=False)
    product.available_quantity = min(product.quantity, product.available_quantity + detail.quantity)

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# ==================== TRANG CHỦ & ĐĂNG NHẬP ====================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('customer_rent'))

@app.route('/health')
def health():
    try:
        db.session.execute(text('SELECT 1'))
        return {'status': 'ok'}, 200
    except Exception:
        return {'status': 'unhealthy'}, 503

@app.route('/robots.txt')
def robots_txt():
    base_url = app.config['PUBLIC_BASE_URL']
    content = (
        "User-agent: *\n"
        "Allow: /rent\n"
        "Disallow: /admin\n"
        "Disallow: /login\n"
        "Disallow: /logout\n"
        "Disallow: /checkout\n"
        "Disallow: /customer/\n\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return Response(content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    base_url = app.config['PUBLIC_BASE_URL']
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/rent</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
'''
    return Response(content, mimetype='application/xml')

@app.route('/admin')
def admin():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/checkout', methods=['GET', 'POST'], endpoint='customer_checkout')
@app.route('/rent', methods=['GET', 'POST'])
def customer_rent():
    customer_account = Customer.query.get(session.get('customer_id')) if session.get('customer_id') else None
    search = request.args.get('q', '').strip()
    selected_category = request.args.get('category', '').strip()
    selected_gender = request.args.get('gender', '').strip().lower()
    selected_size = request.args.get('size', '').strip().upper()
    sort = request.args.get('sort', 'newest')
    filter_start_str = request.args.get('start_date', '').strip()
    filter_end_str = request.args.get('end_date', '').strip()

    filter_start = None
    filter_end = None
    if filter_start_str and filter_end_str:
        try:
            filter_start = datetime.strptime(filter_start_str, '%Y-%m-%d')
            filter_end = datetime.strptime(filter_end_str, '%Y-%m-%d')
            if (filter_end - filter_start).days <= 0:
                filter_start = filter_end = None
        except ValueError:
            filter_start = filter_end = None

    product_query = Product.query.filter(Product.status == 'active')
    if search:
        keyword = f'%{search}%'
        product_query = product_query.filter(or_(
            Product.name.ilike(keyword), Product.description.ilike(keyword),
            Product.category.ilike(keyword)))
    if selected_category:
        selected_node = Category.query.filter_by(name=selected_category).first()
        category_names = [selected_category]
        if selected_node:
            category_names.extend(child.name for child in selected_node.children)
        product_query = product_query.filter(Product.category.in_(category_names))
    if selected_gender in PRODUCT_GENDERS:
        product_query = product_query.filter(or_(
            Product.variants.like(f'%"gender": "{selected_gender}"%'),
            Product.variants.is_(None) & (Product.gender == selected_gender)))
    if selected_size in PRODUCT_SIZES:
        product_query = product_query.filter(Product.sizes.like(f'%|{selected_size}|%'))
    sort_options = {
        'price_asc': Product.price_per_day.asc(),
        'price_desc': Product.price_per_day.desc(),
        'name': Product.name.asc(),
        'newest': Product.created_at.desc()
    }
    raw_products = product_query.order_by(sort_options.get(sort, sort_options['newest'])).all()

    # Tính toán tồn rảnh hiệu lực theo khoảng thời gian nếu người dùng chọn ngày
    booked_quantities = {}
    if filter_start and filter_end:
        overlapping_details = db.session.query(
            RentalDetail.product_id,
            func.sum(RentalDetail.quantity).label('total_booked')
        ).join(Rental).filter(
            Rental.status.in_(['pending', 'rented']),
            func.coalesce(RentalDetail.start_date, Rental.start_date) < filter_end,
            func.coalesce(RentalDetail.end_date, Rental.end_date) > filter_start
        ).group_by(RentalDetail.product_id).all()
        booked_quantities = {row.product_id: (row.total_booked or 0) for row in overlapping_details}

    products = []
    for p in raw_products:
        if filter_start and filter_end:
            booked = booked_quantities.get(p.id, 0)
            effective_avail = max(0, p.quantity - booked)
            if effective_avail > 0:
                p.effective_available_quantity = effective_avail
                products.append(p)
        else:
            if p.available_quantity > 0:
                p.effective_available_quantity = p.available_quantity
                products.append(p)

    categories = [row[0] for row in db.session.query(Product.category).filter(
        Product.status == 'active', Product.category.isnot(None)
    ).distinct().order_by(Product.category).all()]
    category_roots = Category.query.filter_by(parent_id=None).order_by(
        Category.sort_order.asc(), Category.name.asc()).all()

    if request.endpoint == 'customer_checkout' and request.method == 'GET':
        if not customer_account:
            return redirect(url_for('customer_login', next=url_for('customer_checkout')))
        variant_catalog = {}
        for product in Product.query.filter_by(status='active').all():
            variants = product.selectable_variants
            if not variants:
                variants = [{'gender': product.gender or 'unisex', 'size': size,
                             'available': product.available_quantity}
                            for size in product.size_list]
            variant_catalog[str(product.id)] = variants
        return render_template('customer/checkout.html', customer_account=customer_account,
                               filter_start_str=filter_start_str, filter_end_str=filter_end_str,
                               variant_catalog=variant_catalog)

    if request.method == 'POST':
        if not customer_account:
            flash('Vui lòng đăng nhập tài khoản khách hàng trước khi đặt thuê!', 'warning')
            return redirect(url_for('customer_login'))
        fullname = request.form.get('fullname', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        id_card = request.form.get('id_card', '').strip()
        notes = request.form.get('notes', '').strip()
        payment_method = request.form.get('payment_method', 'cash')
        if payment_method not in ('cash', 'bank_transfer'):
            payment_method = 'cash'

        try:
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
        except Exception:
            flash('Ngày thuê không hợp lệ!', 'danger')
            return redirect(url_for('customer_checkout'))

        days = (end_date - start_date).days
        if days <= 0:
            flash('Ngày kết thúc phải sau ngày bắt đầu!', 'danger')
            return redirect(url_for('customer_checkout'))

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        selected_sizes = request.form.getlist('size[]')
        selected_genders = request.form.getlist('gender[]')
        item_start_dates = request.form.getlist('item_start_date[]')
        item_end_dates = request.form.getlist('item_end_date[]')
        # Gom các dòng trùng sản phẩm và luôn kiểm tra tồn kho ở máy chủ.
        cart = {}
        item_schedules = {}
        try:
            if len(product_ids) != len(quantities):
                raise ValueError('Giỏ hàng không hợp lệ!')
            for index, (product_id, raw_quantity) in enumerate(zip(product_ids, quantities)):
                pid = int(product_id)
                quantity = int(raw_quantity)
                if quantity <= 0:
                    raise ValueError('Số lượng thuê phải lớn hơn 0!')
                chosen_size = selected_sizes[index].strip().upper() if index < len(selected_sizes) else ''
                chosen_gender = selected_genders[index].strip().lower() if index < len(selected_genders) else ''
                cart_key = (pid, chosen_gender, chosen_size)
                cart[cart_key] = cart.get(cart_key, 0) + quantity
                raw_start = item_start_dates[index] if index < len(item_start_dates) else ''
                raw_end = item_end_dates[index] if index < len(item_end_dates) else ''
                detail_start = datetime.strptime(raw_start, '%Y-%m-%d') if raw_start else start_date
                detail_end = datetime.strptime(raw_end, '%Y-%m-%d') if raw_end else end_date
                if detail_end <= detail_start:
                    raise ValueError('Ngày trả của từng sản phẩm phải sau ngày nhận!')
                item_schedules[cart_key] = (detail_start, detail_end)
        except (TypeError, ValueError) as exc:
            flash(str(exc) or 'Giỏ hàng không hợp lệ!', 'danger')
            return redirect(url_for('customer_checkout'))

        if not cart:
            flash('Vui lòng chọn ít nhất một sản phẩm!', 'danger')
            return redirect(url_for('customer_checkout'))

        if not fullname or not phone:
            flash('Vui lòng nhập họ tên và số điện thoại!', 'danger')
            return redirect(url_for('customer_checkout'))

        start_date = min(schedule[0] for schedule in item_schedules.values())
        end_date = max(schedule[1] for schedule in item_schedules.values())

        customer = customer_account
        customer.fullname = fullname
        customer.phone = phone
        customer.email = email
        customer.address = address
        customer.id_card = id_card
        customer.notes = notes

        db.session.flush()

        rental_code = f"KH{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
        rental = Rental(
            rental_code=rental_code,
            customer_id=customer.id,
            start_date=start_date,
            end_date=end_date,
            status='pending',
            payment_method=payment_method,
            payment_status='pending_confirmation' if payment_method == 'bank_transfer' else 'unpaid'
        )
        db.session.add(rental)
        db.session.flush()

        total_amount = 0
        try:
            for (product_id, chosen_gender, chosen_size), quantity in cart.items():
                product = Product.query.filter_by(id=product_id, status='active').first()
                if not product:
                    raise ValueError('Có sản phẩm không còn khả dụng!')

                product_variants = product.variant_list
                variant = next((item for item in product_variants
                                if item['gender'] == chosen_gender
                                and (not item.get('size') or item['size'] == chosen_size)), None)
                available = variant['available'] if variant else product.available_quantity
                if product.variant_list and not variant:
                    raise ValueError(f'Vui lòng chọn phân loại và size hợp lệ cho {product.name}!')
                if quantity > available:
                    raise ValueError(f'Sản phẩm {product.name} bản {PRODUCT_GENDERS.get(chosen_gender, chosen_gender)} - {chosen_size} chỉ còn {available}!')

                detail_start, detail_end = item_schedules[(product_id, chosen_gender, chosen_size)]
                detail_days = (detail_end - detail_start).days
                subtotal = product.price_per_day * detail_days * quantity
                total_amount += subtotal

                detail = RentalDetail(
                    rental_id=rental.id,
                    product_id=product_id,
                    quantity=quantity,
                    price_per_day=product.price_per_day,
                    days=detail_days,
                    subtotal=subtotal,
                    start_date=detail_start,
                    end_date=detail_end,
                    selected_size=chosen_size or None,
                    selected_gender=chosen_gender or None
                )
                db.session.add(detail)
                if variant:
                    variant['available'] -= quantity
                    product.variants = json.dumps(product_variants, ensure_ascii=False)
                product.available_quantity -= quantity

            rental.total_amount = total_amount
            db.session.commit()
            flash(f'Tạo đơn thuê thành công! Mã: {rental_code} - Tổng tiền: {total_amount:,.0f}đ', 'success')
            return redirect(url_for('customer_orders'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
            return redirect(url_for('customer_checkout'))

    return render_template('customer/customer_rent.html', products=products, categories=categories,
                           search=search, selected_category=selected_category,
                           selected_gender=selected_gender, selected_size=selected_size,
                           customer_account=customer_account, sort=sort,
                           category_roots=category_roots,
                           filter_start_str=filter_start_str, filter_end_str=filter_end_str)

@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if session.get('customer_id'):
        return redirect(url_for('customer_orders'))
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not fullname or not phone or len(password) < 6:
            flash('Vui lòng nhập đầy đủ thông tin; mật khẩu cần ít nhất 6 ký tự.', 'danger')
        elif Customer.query.filter_by(phone=phone).first() and Customer.query.filter_by(phone=phone).first().password_hash:
            flash('Số điện thoại này đã có tài khoản.', 'danger')
        else:
            customer = Customer.query.filter_by(phone=phone).first()
            if customer:
                customer.fullname = fullname
                customer.email = email
                customer.password_hash = generate_password_hash(password)
            else:
                customer = Customer(fullname=fullname, phone=phone, email=email,
                                    password_hash=generate_password_hash(password))
                db.session.add(customer)
            db.session.commit()
            session['customer_id'] = customer.id
            flash('Tạo tài khoản thành công!', 'success')
            return redirect(url_for('customer_checkout'))
    return render_template('customer/customer_register.html')

@app.route('/customer/login', methods=['GET', 'POST'])
def customer_login():
    next_page = request.args.get('next', '')
    destination = url_for('customer_checkout') if next_page == url_for('customer_checkout') else url_for('customer_rent')
    if session.get('customer_id'):
        return redirect(destination)
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        customer = Customer.query.filter_by(phone=phone).first()
        if customer and customer.password_hash and check_password_hash(customer.password_hash, request.form.get('password', '')):
            session['customer_id'] = customer.id
            return redirect(destination)
        flash('Số điện thoại hoặc mật khẩu không đúng.', 'danger')
    return render_template('customer/customer_login.html')

@app.route('/customer/logout')
def customer_logout():
    session.pop('customer_id', None)
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('customer_rent'))

@app.route('/customer/orders')
def customer_orders():
    customer_id = session.get('customer_id')
    if not customer_id:
        flash('Vui lòng đăng nhập để xem lịch sử thuê.', 'warning')
        return redirect(url_for('customer_login'))
    customer = Customer.query.get_or_404(customer_id)
    orders = Rental.query.filter_by(customer_id=customer.id).order_by(Rental.rental_date.desc()).all()
    active_orders = [order for order in orders if order.status in ('pending', 'rented')]
    completed_orders = [order for order in orders if order.status in ('returned', 'cancelled')]
    return render_template('customer/customer_orders.html', customer=customer, orders=orders,
                           active_orders=active_orders, completed_orders=completed_orders)

@app.route('/customer/orders/<int:id>/payment-proof', methods=['POST'])
def submit_payment_proof(id):
    customer_id = session.get('customer_id')
    if not customer_id:
        flash('Vui lòng đăng nhập để xác nhận thanh toán.', 'warning')
        return redirect(url_for('customer_login'))
    rental = Rental.query.filter_by(id=id, customer_id=customer_id).first_or_404()
    if rental.payment_method != 'bank_transfer' or rental.status == 'cancelled':
        abort(400, description='Đơn hàng không hợp lệ để gửi xác nhận thanh toán.')
    if rental.payment_status == 'paid':
        flash('Đơn này đã được cửa hàng xác nhận thanh toán.', 'info')
        return redirect(url_for('customer_orders'))

    receipt = request.files.get('payment_receipt')
    if not receipt or not receipt.filename:
        flash('Vui lòng chọn ảnh giao dịch trước khi gửi.', 'danger')
        return redirect(url_for('customer_orders'))
    if not allowed_file(receipt.filename) or not (receipt.mimetype or '').startswith('image/'):
        flash('Ảnh giao dịch phải có định dạng PNG, JPG, JPEG, GIF hoặc WEBP.', 'danger')
        return redirect(url_for('customer_orders'))

    extension = secure_filename(receipt.filename).rsplit('.', 1)[1].lower()
    filename = f"receipt_{rental.id}_{secrets.token_hex(8)}.{extension}"
    receipt_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'payment_receipts')
    os.makedirs(receipt_folder, exist_ok=True)
    receipt.save(os.path.join(receipt_folder, filename))
    rental.payment_receipt_url = url_for('static', filename=f'uploads/payment_receipts/{filename}')
    rental.payment_submitted_at = datetime.now()
    rental.payment_status = 'customer_submitted'
    db.session.commit()
    flash('Đã gửi ảnh giao dịch. Cửa hàng sẽ kiểm tra và xác nhận sớm.', 'success')
    return redirect(url_for('customer_orders'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and check_password_hash(admin.password, password):
            login_user(admin)
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Sai tên đăng nhập hoặc mật khẩu!', 'danger')
    
    return render_template('admin/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Đã đăng xuất', 'info')
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================
@app.route('/dashboard')
@login_required
def dashboard():
    total_customers = Customer.query.count()
    total_products = Product.query.count()
    total_rentals = Rental.query.count()
    active_rentals = Rental.query.filter(Rental.status.in_(['pending', 'rented'])).count()
    total_revenue = db.session.query(func.sum(Rental.total_amount)).filter(
        Rental.status == 'returned').scalar() or 0
    low_stock = Product.query.filter(Product.available_quantity <= 2, Product.status == 'active').count()
    recent_rentals = Rental.query.order_by(Rental.rental_date.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_customers=total_customers,
                         total_products=total_products,
                         total_rentals=total_rentals,
                         active_rentals=active_rentals, total_revenue=total_revenue,
                         low_stock=low_stock, recent_rentals=recent_rentals)

# ==================== QUẢN LÝ KHÁCH HÀNG ====================
@app.route('/customers')
@login_required
def customers():
    all_customers = Customer.query.all()
    return render_template('admin/customers.html', customers=all_customers)

@app.route('/add-customer', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        phone = request.form.get('phone', '').strip()
        if not fullname or not phone:
            flash('Vui lòng nhập họ tên và số điện thoại!', 'danger')
            return redirect(url_for('add_customer'))
        if Customer.query.filter_by(phone=phone).first():
            flash('Số điện thoại này đã tồn tại!', 'warning')
            return redirect(url_for('add_customer'))
        customer = Customer(
            fullname=fullname,
            phone=phone,
            email=request.form.get('email', ''),
            address=request.form.get('address', '')
        )
        db.session.add(customer)
        db.session.commit()
        flash('Thêm khách hàng thành công!', 'success')
        return redirect(url_for('customers'))
    return render_template('admin/add_customer.html')

@app.route('/delete-customer/<int:id>', methods=['POST'])
@login_required
def delete_customer(id):
    customer = Customer.query.get_or_404(id)
    if customer.rentals:
        flash('Không thể xóa khách hàng đã có đơn thuê!', 'danger')
        return redirect(url_for('customers'))
    db.session.delete(customer)
    db.session.commit()
    flash('Xóa khách hàng thành công!', 'success')
    return redirect(url_for('customers'))

# ==================== QUẢN LÝ SẢN PHẨM ====================
@app.route('/products')
@login_required
def products():
    selected_category = request.args.get('category', '')
    query = Product.query
    if selected_category:
        query = query.filter_by(category=selected_category)

    all_products = query.all()
    categories = Product.query.with_entities(Product.category).distinct().all()
    categories = [{'category': item[0]} for item in categories if item[0]]

    return render_template('admin/products.html', products=all_products, categories=categories, selected_category=selected_category)

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def add_category():
    if request.method == 'POST':
        name = request.form.get('category_name', '').strip()
        parent_id = request.form.get('parent_id', '').strip()
        if not name:
            flash('Vui lòng nhập tên danh mục!', 'danger')
        elif Category.query.filter_by(name=name).first():
            flash('Tên danh mục này đã tồn tại!', 'warning')
        else:
            parent = Category.query.get(int(parent_id)) if parent_id else None
            category = Category(name=name, parent=parent,
                                sort_order=request.form.get('sort_order', type=int) or 0)
            db.session.add(category)
            db.session.commit()
            flash(f'Đã thêm danh mục “{name}”!', 'success')
            return redirect(url_for('add_category'))
    roots = Category.query.filter_by(parent_id=None).order_by(
        Category.sort_order.asc(), Category.name.asc()).all()
    return render_template('admin/add_category.html', categories=roots)

@app.route('/delete-category/<int:id>', methods=['POST'])
@login_required
def delete_category(id):
    category = Category.query.get_or_404(id)
    used_names = [category.name] + [child.name for child in category.children]
    if Product.query.filter(Product.category.in_(used_names)).first():
        flash('Không thể xóa danh mục đang có sản phẩm!', 'danger')
    else:
        db.session.delete(category)
        db.session.commit()
        flash('Đã xóa danh mục!', 'success')
    return redirect(url_for('add_category'))

@app.route('/add-product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        try:
            image_url = product_image_from_request()
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('add_product'))
        
        try:
            category = category_from_form()
            variants = product_variants_from_form()
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('add_product'))

        try:
            name = request.form.get('name', '').strip()
            price_per_day = float(request.form.get('price_per_day', ''))
            deposit = float(request.form.get('deposit') or 0)
            if not name or price_per_day < 0 or deposit < 0:
                raise ValueError
        except (TypeError, ValueError):
            db.session.rollback()
            flash('Tên, giá thuê, tiền cọc hoặc số lượng không hợp lệ!', 'danger')
            return redirect(url_for('add_product'))

        product = Product(
            name=name,
            category=category,
            description=request.form.get('description', ''),
            price_per_day=price_per_day,
            deposit=deposit,
            image_url=image_url if image_url else None,
            status='active'
        )
        update_product_variants(product, variants)
        db.session.add(product)
        db.session.commit()
        flash('Thêm sản phẩm thành công!', 'success')
        return redirect(url_for('products'))
    
    return render_template('admin/add_product.html', categories=get_product_categories(),
                           genders=PRODUCT_GENDERS, sizes=PRODUCT_SIZES)

@app.route('/edit-product/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        product.name = request.form['name']
        try:
            product.category = category_from_form()
            variants = product_variants_from_form()
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('edit_product', id=id))
        product.description = request.form.get('description', '')
        product.price_per_day = float(request.form['price_per_day'])
        product.deposit = float(request.form.get('deposit', 0))
        try:
            update_product_variants(product, variants)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('edit_product', id=id))
        
        try:
            product.image_url = product_image_from_request(product.image_url)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('edit_product', id=id))
        
        db.session.commit()
        flash('Cập nhật sản phẩm thành công!', 'success')
        return redirect(url_for('products'))
    
    return render_template('admin/edit_product.html', product=product,
                           categories=get_product_categories(), genders=PRODUCT_GENDERS,
                           sizes=PRODUCT_SIZES)

@app.route('/delete-product/<int:id>', methods=['POST'])
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    if product.rental_details:
        product.status = 'inactive'
        db.session.commit()
        flash('Sản phẩm đã phát sinh đơn thuê nên được chuyển sang ngừng hoạt động thay vì xóa.', 'warning')
        return redirect(url_for('products'))
    db.session.delete(product)
    db.session.commit()
    flash('Xóa sản phẩm thành công!', 'success')
    return redirect(url_for('products'))

@app.route('/product-detail/<int:id>')
@login_required
def product_detail(id):
    product = Product.query.get_or_404(id)
    return render_template('admin/product_detail.html', product=product)

# ==================== QUẢN LÝ ĐƠN THUÊ ====================
@app.route('/rentals')
@login_required
def rentals():
    all_rentals = Rental.query.order_by(Rental.rental_date.desc()).all()
    return render_template('admin/rentals.html', rentals=all_rentals)

@app.route('/rentals/<int:id>/invoice')
@login_required
def rental_invoice(id):
    rental = Rental.query.get_or_404(id)
    return render_template('admin/invoice.html', rental=rental)

@app.route('/rentals/<int:id>/confirm-payment', methods=['POST'])
@login_required
def confirm_rental_payment(id):
    rental = Rental.query.get_or_404(id)
    if rental.payment_method != 'bank_transfer':
        flash('Đơn này không chọn thanh toán chuyển khoản.', 'warning')
    elif rental.payment_status == 'paid':
        flash('Đơn này đã được xác nhận thanh toán.', 'warning')
    elif rental.status == 'cancelled':
        flash('Không thể xác nhận thanh toán cho đơn đã hủy.', 'danger')
    else:
        rental.payment_status = 'paid'
        rental.paid_at = datetime.now()
        db.session.commit()
        flash(f'Đã xác nhận thanh toán đơn {rental.rental_code}.', 'success')
    return redirect(url_for('rentals'))

@app.route('/add-rental', methods=['GET', 'POST'])
@login_required
def add_rental():
    if request.method == 'POST':
        customer_mode = request.form.get('customer_mode', 'guest')
        if customer_mode == 'existing' and request.form.get('customer_id'):
            customer = Customer.query.get_or_404(int(request.form['customer_id']))
        else:
            guest_name = request.form.get('guest_name', '').strip()
            guest_phone = request.form.get('guest_phone', '').strip()
            if not guest_name or not guest_phone:
                flash('Khách vãng lai cần có họ tên và số điện thoại!', 'danger')
                return redirect(url_for('add_rental'))
            customer = Customer.query.filter_by(phone=guest_phone).first()
            if customer:
                customer.fullname = guest_name
            else:
                customer = Customer(fullname=guest_name, phone=guest_phone)
                db.session.add(customer)
                db.session.flush()

        try:
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
        except (KeyError, ValueError):
            flash('Ngày thuê không hợp lệ!', 'danger')
            return redirect(url_for('add_rental'))
        
        days = (end_date - start_date).days
        if days <= 0:
            flash('Ngày kết thúc phải sau ngày bắt đầu!', 'danger')
            return redirect(url_for('add_rental'))
        
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        selected_sizes = request.form.getlist('size[]')
        selected_genders = request.form.getlist('gender[]')
        item_start_dates = request.form.getlist('item_start_date[]')
        item_end_dates = request.form.getlist('item_end_date[]')
        
        if not product_ids or len(product_ids) != len(quantities):
            flash('Vui lòng chọn ít nhất 1 sản phẩm!', 'danger')
            return redirect(url_for('add_rental'))
        try:
            product_ids = [int(value) for value in product_ids]
            quantities = [int(value) for value in quantities]
            if any(quantity <= 0 for quantity in quantities):
                raise ValueError
        except (TypeError, ValueError):
            flash('Danh sách sản phẩm hoặc số lượng không hợp lệ!', 'danger')
            return redirect(url_for('add_rental'))
        
        rental_code = f"HD{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
        
        rental = Rental(
            rental_code=rental_code,
            customer_id=customer.id,
            start_date=start_date,
            end_date=end_date,
            status='pending'
        )
        db.session.add(rental)
        db.session.flush()
        
        total_amount = 0
        schedule_start = start_date
        schedule_end = end_date
        
        for i in range(len(product_ids)):
            product_id = product_ids[i]
            quantity = quantities[i]
                
            product = Product.query.get(product_id)
            if not product or product.status != 'active':
                flash('Có sản phẩm không còn khả dụng!', 'danger')
                db.session.rollback()
                return redirect(url_for('add_rental'))

            chosen_size = selected_sizes[i].strip().upper() if i < len(selected_sizes) else ''
            chosen_gender = selected_genders[i].strip().lower() if i < len(selected_genders) else ''
            product_variants = product.variant_list
            variant = next((item for item in product_variants
                            if item['gender'] == chosen_gender
                            and (not item.get('size') or item['size'] == chosen_size)), None)
            if product_variants and not variant:
                flash(f'Vui lòng chọn phân loại và size hợp lệ cho {product.name}!', 'danger')
                db.session.rollback()
                return redirect(url_for('add_rental'))
            
            available = variant['available'] if variant else product.available_quantity
            if quantity > available:
                flash(f'Sản phẩm {product.name} chỉ còn {product.available_quantity}!', 'danger')
                db.session.rollback()
                return redirect(url_for('add_rental'))
            
            detail_start = start_date
            detail_end = end_date
            if i < len(item_start_dates) and i < len(item_end_dates):
                raw_item_start = item_start_dates[i].strip()
                raw_item_end = item_end_dates[i].strip()
                if raw_item_start or raw_item_end:
                    if not raw_item_start or not raw_item_end:
                        flash(f'Vui lòng chọn đủ ngày nhận và trả riêng cho {product.name}!', 'danger')
                        db.session.rollback()
                        return redirect(url_for('add_rental'))
                    try:
                        detail_start = datetime.strptime(raw_item_start, '%Y-%m-%d')
                        detail_end = datetime.strptime(raw_item_end, '%Y-%m-%d')
                    except ValueError:
                        flash(f'Ngày thuê riêng của {product.name} không hợp lệ!', 'danger')
                        db.session.rollback()
                        return redirect(url_for('add_rental'))
            detail_days = (detail_end - detail_start).days
            if detail_days <= 0:
                flash(f'Ngày trả riêng của {product.name} phải sau ngày nhận!', 'danger')
                db.session.rollback()
                return redirect(url_for('add_rental'))

            schedule_start = min(schedule_start, detail_start)
            schedule_end = max(schedule_end, detail_end)

            subtotal = product.price_per_day * detail_days * quantity
            total_amount += subtotal
            
            detail = RentalDetail(
                rental_id=rental.id,
                product_id=product_id,
                quantity=quantity,
                price_per_day=product.price_per_day,
                days=detail_days,
                subtotal=subtotal,
                start_date=detail_start,
                end_date=detail_end,
                selected_size=chosen_size or None,
                selected_gender=chosen_gender or None
            )
            db.session.add(detail)
            
            if variant:
                variant['available'] -= quantity
                product.variants = json.dumps(product_variants, ensure_ascii=False)
            product.available_quantity -= quantity
        
        rental.total_amount = total_amount
        rental.start_date = schedule_start
        rental.end_date = schedule_end
        db.session.commit()
        
        flash(f'Tạo đơn thuê thành công! Mã: {rental_code} - Tổng tiền: {total_amount:,.0f}đ', 'success')
        return redirect(url_for('rentals'))
    
    customers = Customer.query.all()
    products = Product.query.filter(Product.available_quantity > 0).all()
    return render_template('admin/add_rental.html', customers=customers, products=products)

@app.route('/return-rental/<int:id>', methods=['POST'])
@login_required
def return_rental(id):
    rental = Rental.query.get_or_404(id)
    if rental.status != 'rented':
        flash('Chỉ có thể nhận trả sau khi đơn đã được soạn xong!', 'danger')
        return redirect(url_for('rentals'))
    rental.status = 'returned'
    rental.actual_return_date = datetime.now()
    
    for detail in rental.details:
        product = Product.query.get(detail.product_id)
        if product:
            restore_detail_inventory(product, detail)
    
    db.session.commit()
    flash('Đã xác nhận trả hàng!', 'success')
    return redirect(url_for('rentals'))

@app.route('/prepare-rental/<int:id>', methods=['POST'])
@login_required
def prepare_rental(id):
    rental = Rental.query.get_or_404(id)
    if rental.status != 'pending':
        flash('Đơn này không còn ở trạng thái chờ soạn.', 'warning')
        return redirect(url_for('rentals'))
    rental.status = 'rented'
    db.session.commit()
    flash(f'Đơn {rental.rental_code} đã soạn xong và chuyển sang chờ khách trả!', 'success')
    return redirect(url_for('rentals'))

@app.route('/cancel-rental/<int:id>', methods=['POST'])
@login_required
def cancel_rental(id):
    rental = Rental.query.get_or_404(id)
    
    if rental.status in ['pending', 'rented']:
        rental.status = 'cancelled'
        
        for detail in rental.details:
            product = Product.query.get(detail.product_id)
            if product:
                restore_detail_inventory(product, detail)
        
        db.session.commit()
        flash(f'Đã hủy đơn thuê {rental.rental_code}!', 'success')
    else:
        flash('Không thể hủy đơn này!', 'danger')
    
    return redirect(url_for('rentals'))

@app.route('/delete-rental/<int:id>', methods=['POST'])
@login_required
def delete_rental(id):
    rental = Rental.query.get_or_404(id)
    
    if rental.status in ['returned', 'cancelled']:
        rental_code = rental.rental_code
        db.session.delete(rental)
        db.session.commit()
        flash(f'Đã xóa đơn thuê {rental_code}!', 'success')
    else:
        flash('Không thể xóa đơn đang thuê!', 'danger')
    
    return redirect(url_for('rentals'))

# ==================== BÁO CÁO ====================
def get_revenue_by_date_range(start_date, end_date):
    try:
        result = db.session.query(func.sum(Rental.total_amount)).filter(
            Rental.status == 'returned',
            Rental.actual_return_date >= start_date,
            Rental.actual_return_date < end_date
        ).scalar()
        return float(result) if result else 0
    except Exception as e:
        return 0

@app.route('/reports')
@login_required
def reports():
    report_type = request.args.get('report_type', 'month')
    today = datetime.now()
    default_periods = {
        'day': today.strftime('%Y-%m-%d'),
        'week': (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d'),
        'month': today.strftime('%Y-%m'),
        'year': str(today.year),
    }
    if report_type not in default_periods:
        report_type = 'month'
    period = request.args.get('period') or default_periods[report_type]
    try:
        if report_type in ('day', 'week'):
            datetime.strptime(period, '%Y-%m-%d')
        elif report_type == 'month':
            datetime.strptime(period, '%Y-%m')
        else:
            year_value = int(period)
            if not 2000 <= year_value <= 2100:
                raise ValueError
    except (TypeError, ValueError):
        flash('Khoảng thời gian báo cáo không hợp lệ.', 'danger')
        return redirect(url_for('reports', report_type=report_type,
                                period=default_periods[report_type]))

    labels = []
    revenue_data = []
    start_date = None
    end_date = None
    
    # Xử lý theo loại báo cáo
    if report_type == 'day':
        if period:
            start_date = datetime.strptime(period, '%Y-%m-%d')
        else:
            start_date = today
        end_date = start_date + timedelta(days=1)
        labels = [start_date.strftime('%d/%m/%Y')]
        revenue_data = [get_revenue_by_date_range(start_date, end_date)]
        
    elif report_type == 'week':
        if period:
            start_date = datetime.strptime(period, '%Y-%m-%d')
        else:
            start_date = today - timedelta(days=today.weekday())
        labels = []
        revenue_data = []
        for i in range(7):
            day_start = start_date + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            labels.append(day_start.strftime('%d/%m'))
            revenue_data.append(get_revenue_by_date_range(day_start, day_end))
        end_date = start_date + timedelta(days=7)
        
    elif report_type == 'year':
        year = int(period) if period else today.year
        labels = [f'Tháng {i}' for i in range(1, 13)]
        revenue_data = []
        for month in range(1, 13):
            month_start = datetime(year, month, 1)
            if month == 12:
                month_end = datetime(year + 1, 1, 1)
            else:
                month_end = datetime(year, month + 1, 1)
            revenue_data.append(get_revenue_by_date_range(month_start, month_end))
        start_date = datetime(year, 1, 1)
        end_date = datetime(year + 1, 1, 1)
        
    else:  # month
        if period and '-' in period:
            year, month = map(int, period.split('-'))
        else:
            year, month = today.year, today.month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        labels = []
        revenue_data = []
        week_start = start_date
        week_num = 1
        while week_start < end_date:
            week_end = min(week_start + timedelta(days=7), end_date)
            labels.append(f'Tuần {week_num}')
            revenue_data.append(get_revenue_by_date_range(week_start, week_end))
            week_start = week_end
            week_num += 1
    
    # Tính tổng doanh thu
    total_revenue = sum(revenue_data)
    
    # Tổng số đơn đã trả
    if start_date and end_date:
        total_rentals = Rental.query.filter(
            Rental.status == 'returned',
            Rental.actual_return_date >= start_date,
            Rental.actual_return_date < end_date
        ).count()
        
        unique_customers = db.session.query(Rental.customer_id).filter(
            Rental.status == 'returned',
            Rental.actual_return_date >= start_date,
            Rental.actual_return_date < end_date
        ).distinct().count()
    else:
        total_rentals = Rental.query.filter_by(status='returned').count()
        unique_customers = db.session.query(Rental.customer_id).distinct().count()
    
    avg_per_rental = total_revenue / total_rentals if total_rentals > 0 else 0
    
    # TOP KHÁCH HÀNG THÂN THIẾT
    top_customers = db.session.query(
        Customer,
        func.count(Rental.id).label('rental_count'),
        func.sum(Rental.total_amount).label('total_amount')
    ).join(Rental).filter(
        Rental.status == 'returned'
    ).group_by(Customer.id).order_by(db.desc('total_amount')).limit(10).all()
    
    top_customers_list = []
    for customer, rental_count, total_amount in top_customers:
        top_customers_list.append({
            'fullname': customer.fullname,
            'phone': customer.phone,
            'rental_count': rental_count,
            'total_amount': float(total_amount) if total_amount else 0
        })
    
    # THỐNG KÊ THEO DANH MỤC - ĐÃ SỬA
    try:
        category_stats = db.session.query(
            Product.category,
            func.sum(RentalDetail.subtotal).label('total')
        ).join(RentalDetail, Product.id == RentalDetail.product_id)\
         .join(Rental, Rental.id == RentalDetail.rental_id)\
         .filter(Rental.status == 'returned')\
         .group_by(Product.category).all()
        
        category_labels = [stat[0] for stat in category_stats if stat[0]]
        category_data = [float(stat[1]) for stat in category_stats if stat[1]]
    except:
        category_labels = []
        category_data = []
    
    # TOP SẢN PHẨM CHO THUÊ NHIỀU NHẤT
    try:
        top_products = db.session.query(
            Product.name,
            func.count(RentalDetail.id).label('count')
        ).join(RentalDetail).join(Rental).filter(
            Rental.status == 'returned'
        ).group_by(Product.id).order_by(func.count(RentalDetail.id).desc()).limit(5).all()
        
        product_labels = [p[0] for p in top_products]
        product_rental_counts = [p[1] for p in top_products]
    except:
        product_labels = []
        product_rental_counts = []
    
    return render_template('admin/reports.html',
                         report_type=report_type,
                         period=period,
                         start_date=start_date.strftime('%d/%m/%Y') if start_date else '',
                         end_date=end_date.strftime('%d/%m/%Y') if end_date else '',
                         total_revenue=total_revenue,
                         total_rentals=total_rentals,
                         unique_customers=unique_customers,
                         avg_per_rental=avg_per_rental,
                         labels=labels,
                         revenue_data=revenue_data,
                         category_labels=category_labels,
                         category_data=category_data,
                         product_labels=product_labels,
                         product_rental_counts=product_rental_counts,
                         top_customers=top_customers_list)

# ==================== EXPORT ====================
@app.route('/export-excel')
@login_required
def export_excel():
    import pandas as pd
    from io import BytesIO
    
    data = []
    rentals = Rental.query.filter(Rental.status == 'returned').all()
    for rental in rentals:
        for detail in rental.details:
            data.append({
                'Mã đơn': rental.rental_code,
                'Khách hàng': rental.customer.fullname,
                'Sản phẩm': detail.product.name,
                'Số lượng': detail.quantity,
                'Ngày thuê': rental.rental_date.strftime('%d/%m/%Y'),
                'Ngày bắt đầu': rental.start_date.strftime('%d/%m/%Y'),
                'Ngày kết thúc': rental.end_date.strftime('%d/%m/%Y'),
                'Thành tiền': detail.subtotal
            })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Doanh thu', index=False)
    
    output.seek(0)
    filename = f'report_{datetime.now().strftime("%Y%m%d")}.xlsx'
    return Response(
        FileWrapper(output), direct_passthrough=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

@app.route('/export-pdf')
@login_required
def export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from io import BytesIO
    
    rentals = Rental.query.filter(Rental.status == 'returned').all()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30)
    styles = getSampleStyleSheet()
    elements = []
    
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#667eea'))
    elements.append(Paragraph("BÁO CÁO DOANH THU", title_style))
    elements.append(Spacer(1, 20))
    
    data = [['Mã đơn', 'Khách hàng', 'Sản phẩm', 'Ngày thuê', 'Thành tiền']]
    for rental in rentals[:50]:
        for detail in rental.details:
            data.append([
                rental.rental_code,
                rental.customer.fullname,
                detail.product.name,
                rental.rental_date.strftime('%d/%m/%Y'),
                f"{detail.subtotal:,.0f} VNĐ"
            ])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    
    filename = f'report_{datetime.now().strftime("%Y%m%d")}.pdf'
    return Response(
        FileWrapper(buffer), direct_passthrough=True, mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

# ==================== KHỞI TẠO DATABASE ====================
def init_db():
    with app.app_context():
        db.create_all()
        # Bổ sung cột cho database cũ mà không làm mất dữ liệu.
        columns = [row[1] for row in db.session.execute(text('PRAGMA table_info(customer)')).fetchall()]
        if 'password_hash' not in columns:
            db.session.execute(text('ALTER TABLE customer ADD COLUMN password_hash VARCHAR(200)'))
            db.session.commit()
        product_columns = [row[1] for row in db.session.execute(text('PRAGMA table_info(product)')).fetchall()]
        if 'gender' not in product_columns:
            db.session.execute(text("ALTER TABLE product ADD COLUMN gender VARCHAR(20) DEFAULT 'unisex'"))
        if 'sizes' not in product_columns:
            db.session.execute(text('ALTER TABLE product ADD COLUMN sizes VARCHAR(100)'))
        if 'variants' not in product_columns:
            db.session.execute(text('ALTER TABLE product ADD COLUMN variants TEXT'))
        detail_columns = [row[1] for row in db.session.execute(text('PRAGMA table_info(rental_detail)')).fetchall()]
        if 'start_date' not in detail_columns:
            db.session.execute(text('ALTER TABLE rental_detail ADD COLUMN start_date DATETIME'))
        if 'end_date' not in detail_columns:
            db.session.execute(text('ALTER TABLE rental_detail ADD COLUMN end_date DATETIME'))
        if 'selected_size' not in detail_columns:
            db.session.execute(text('ALTER TABLE rental_detail ADD COLUMN selected_size VARCHAR(10)'))
        if 'selected_gender' not in detail_columns:
            db.session.execute(text('ALTER TABLE rental_detail ADD COLUMN selected_gender VARCHAR(20)'))
        rental_columns = [row[1] for row in db.session.execute(text('PRAGMA table_info(rental)')).fetchall()]
        if 'payment_method' not in rental_columns:
            db.session.execute(text("ALTER TABLE rental ADD COLUMN payment_method VARCHAR(20) DEFAULT 'cash'"))
        if 'payment_status' not in rental_columns:
            db.session.execute(text("ALTER TABLE rental ADD COLUMN payment_status VARCHAR(30) DEFAULT 'unpaid'"))
        if 'paid_at' not in rental_columns:
            db.session.execute(text('ALTER TABLE rental ADD COLUMN paid_at DATETIME'))
        if 'payment_receipt_url' not in rental_columns:
            db.session.execute(text('ALTER TABLE rental ADD COLUMN payment_receipt_url VARCHAR(300)'))
        if 'payment_submitted_at' not in rental_columns:
            db.session.execute(text('ALTER TABLE rental ADD COLUMN payment_submitted_at DATETIME'))
        db.session.commit()
        
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        existing_admin = Admin.query.filter_by(username=admin_username).first()
        if not existing_admin:
            admin = Admin(
                username=admin_username,
                password=generate_password_hash(admin_password),
                email='admin@example.com',
                fullname='Administrator'
            )
            db.session.add(admin)
        elif os.environ.get('ADMIN_PASSWORD'):
            existing_admin.password = generate_password_hash(admin_password)
        
        db.session.commit()
        print("Database created successfully!")
        print(f"Admin account initialized: {admin_username}")

if __name__ == '__main__':
    init_db()
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
