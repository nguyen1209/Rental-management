from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from models import db, Admin, Customer, Product, Rental
import os
from werkzeug.utils import secure_filename
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rental.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/add-product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        # Xử lý upload ảnh
        image_url = request.form.get('image_url', '')
        
        # Kiểm tra nếu có upload file
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                # Tạo tên file an toàn
                filename = secure_filename(file.filename)
                # Thêm timestamp để tránh trùng tên
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                # Lưu file
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                # Lưu đường dẫn vào database
                image_url = url_for('static', filename=f'uploads/{filename}')
        
        product = Product(
            name=request.form['name'],
            category=request.form['category'],
            description=request.form.get('description', ''),
            price_per_day=float(request.form['price_per_day']),
            deposit=float(request.form.get('deposit', 0)),
            quantity=int(request.form['quantity']),
            available_quantity=int(request.form['quantity']),
            image_url=image_url if image_url else None,
            status='active'
        )
        db.session.add(product)
        db.session.commit()
        flash('Thêm sản phẩm thành công!', 'success')
        return redirect(url_for('products'))
    
    return render_template('add_product.html')
@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# Trang chủ
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Đăng nhập
@app.route('/login', methods=['GET', 'POST'])
def login():
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
    
    return render_template('login.html')

# Đăng xuất
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Đã đăng xuất', 'info')
    return redirect(url_for('login'))

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    total_customers = Customer.query.count()
    total_products = Product.query.count()
    total_rentals = Rental.query.count()
    active_rentals = Rental.query.filter_by(status='rented').count()
    
    return render_template('dashboard.html', 
                         total_customers=total_customers,
                         total_products=total_products,
                         total_rentals=total_rentals,
                         active_rentals=active_rentals)

# Quản lý khách hàng
@app.route('/customers')
@login_required
def customers():
    all_customers = Customer.query.all()
    return render_template('customers.html', customers=all_customers)

@app.route('/add-customer', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        customer = Customer(
            fullname=request.form['fullname'],
            phone=request.form['phone'],
            email=request.form.get('email', ''),
            address=request.form.get('address', '')
        )
        db.session.add(customer)
        db.session.commit()
        flash('Thêm khách hàng thành công!', 'success')
        return redirect(url_for('customers'))
    return render_template('add_customer.html')

@app.route('/delete-customer/<int:id>')
@login_required
def delete_customer(id):
    customer = Customer.query.get_or_404(id)
    db.session.delete(customer)
    db.session.commit()
    flash('Xóa khách hàng thành công!', 'success')
    return redirect(url_for('customers'))

# Quản lý sản phẩm
@app.route('/products')
@login_required
def products():
    all_products = Product.query.all()
    return render_template('products.html', products=all_products)


@app.route('/delete-product/<int:id>')
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Xóa sản phẩm thành công!', 'success')
    return redirect(url_for('products'))
@app.route('/product-detail/<int:id>')
@login_required
def product_detail(id):
    product = Product.query.get_or_404(id)
    return render_template('product_detail.html', product=product)
# Quản lý đơn thuê
@app.route('/rentals')
@login_required
def rentals():
    all_rentals = Rental.query.all()
    return render_template('rentals.html', rentals=all_rentals)

@app.route('/add-rental', methods=['GET', 'POST'])
@login_required
def add_rental():
    if request.method == 'POST':
        customer_id = int(request.form['customer_id'])
        product_id = int(request.form['product_id'])
        quantity = int(request.form['quantity'])
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
        
        # Lấy thông tin sản phẩm
        product = Product.query.get(product_id)
        
        # Kiểm tra số lượng
        if quantity > product.quantity:
            flash(f'Số lượng không đủ, chỉ còn {product.quantity} sản phẩm', 'danger')
            return redirect(url_for('add_rental'))
        
        # Tính số ngày thuê
        days = (end_date - start_date).days
        if days <= 0:
            flash('Ngày kết thúc phải sau ngày bắt đầu', 'danger')
            return redirect(url_for('add_rental'))
        
        # Tính tiền
        price_per_day = product.price_per_day
        total_price = price_per_day * days * quantity
        deposit_amount = product.price_per_day * quantity  # Hoặc bạn có thể set tiền cọc riêng
        
        # Tạo mã đơn
        rental_code = f"HD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Tạo đơn thuê
        rental = Rental(
            rental_code=rental_code,
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
            start_date=start_date,
            end_date=end_date,
            price_per_day=price_per_day,  # Quan trọng: phải có giá trị
            deposit_amount=deposit_amount,  # Quan trọng: phải có giá trị
            total_price=total_price,  # Quan trọng: phải có giá trị
            status='rented'
        )
        
        # Cập nhật số lượng sản phẩm
        product.quantity -= quantity
        
        db.session.add(rental)
        db.session.commit()
        
        flash(f'Thêm đơn thuê thành công! Mã đơn: {rental_code}', 'success')
        return redirect(url_for('rentals'))
    
    customers = Customer.query.all()
    products = Product.query.filter(Product.quantity > 0).all()
    return render_template('add_rental.html', customers=customers, products=products)

@app.route('/edit-product/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    
    if request.method == 'POST':
        product.name = request.form['name']
        product.category = request.form['category']
        product.description = request.form.get('description', '')
        product.price_per_day = float(request.form['price_per_day'])
        product.deposit = float(request.form.get('deposit', 0))
        product.quantity = int(request.form['quantity'])
        
        # Xử lý upload ảnh mới
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                # Xóa ảnh cũ nếu có (tùy chọn)
                if product.image_url and product.image_url.startswith('/static/uploads/'):
                    old_filepath = product.image_url.replace('/static/', 'static/')
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                
                # Upload ảnh mới
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                product.image_url = url_for('static', filename=f'uploads/{filename}')
        
        # Nếu có URL từ input text
        image_url_input = request.form.get('image_url', '')
        if image_url_input:
            product.image_url = image_url_input
        
        db.session.commit()
        flash('Cập nhật sản phẩm thành công!', 'success')
        return redirect(url_for('products'))
    
    return render_template('edit_product.html', product=product)
@app.route('/return-rental/<int:id>')
@login_required
def return_rental(id):
    rental = Rental.query.get_or_404(id)
    rental.status = 'returned'
    db.session.commit()
    flash('Đã xác nhận trả hàng!', 'success')
    return redirect(url_for('rentals'))

# Tạo database và dữ liệu mẫu
def init_db():
    with app.app_context():
        db.create_all()
        
        # Tạo admin nếu chưa có
        if not Admin.query.first():
            admin = Admin(
                username='admin',
                password=generate_password_hash('admin123'),
                fullname='Admin'
            )
            db.session.add(admin)
        
        # Thêm dữ liệu mẫu
        if Customer.query.count() == 0:
            customers = [
                Customer(fullname='Nguyễn Văn A', phone='0901234567', email='a@gmail.com', address='Hà Nội'),
                Customer(fullname='Trần Thị B', phone='0912345678', email='b@gmail.com', address='TP HCM'),
            ]
            for c in customers:
                db.session.add(c)
        
        if Product.query.count() == 0:
            products = [
                Product(name='Guitar', category='Nhạc cụ', price_per_day=150000, quantity=5),
                Product(name='Micro', category='Âm thanh', price_per_day=200000, quantity=3),
                Product(name='Loa kéo', category='Âm thanh', price_per_day=300000, quantity=2),
            ]
            for p in products:
                db.session.add(p)
        
        db.session.commit()
        print("Database created successfully!")
        print("Admin account: admin / admin123")

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 