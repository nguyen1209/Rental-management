from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from models import db, Admin, Customer, Product, Rental
import os
from werkzeug.utils import secure_filename
import calendar
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
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from flask import send_file, Response


@app.route('/reports')
@login_required
def reports():
    # Lấy tham số từ request
    report_type = request.args.get('report_type', 'month')
    period = request.args.get('period', datetime.now().strftime('%Y-%m'))
    
    # Xác định khoảng thời gian
    today = datetime.now()
    if report_type == 'day':
        if period:
            start_date = datetime.strptime(period, '%Y-%m-%d')
            end_date = start_date + timedelta(days=1)
            labels = [start_date.strftime('%d/%m/%Y')]
            revenue_data = [get_revenue_by_date_range(start_date, end_date)]
        else:
            start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
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
        year = int(period.split('-')[0]) if period else today.year
        labels = [f'Tháng {i}' for i in range(1, 13)]
        revenue_data = []
        for month in range(1, 13):
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, month + 1, 1)
            revenue_data.append(get_revenue_by_date_range(start_date, end_date))
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
    
    else:  # month
        if period:
            year, month= map(int, period.split('-'))
        else:
            year, month = today.year, today.month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        labels = [f'Tuần {i+1}' for i in range(4)]
        revenue_data = []
        for week in range(4):
            week_start = start_date + timedelta(days=week*7)
            week_end = min(week_start + timedelta(days=7), end_date)
            revenue_data.append(get_revenue_by_date_range(week_start, week_end))
    
    # Tính tổng doanh thu
    total_revenue = sum(revenue_data)
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
    
    avg_per_rental = total_revenue / total_rentals if total_rentals > 0 else 0
    
    # Thống kê theo danh mục
    category_stats = db.session.query(
        Product.category,
        db.func.sum(Rental.total_price).label('total')
    ).join(Rental).filter(
        Rental.status == 'returned',
        Rental.actual_return_date >= start_date,
        Rental.actual_return_date < end_date
    ).group_by(Product.category).all()
    
    category_labels = [stat[0] for stat in category_stats]
    category_data = [float(stat[1]) for stat in category_stats]
    
    # Top sản phẩm cho thuê nhiều nhất
    top_products = db.session.query(
        Product.name,
        db.func.count(Rental.id).label('count')
    ).join(Rental).filter(
        Rental.status == 'returned',
        Rental.actual_return_date >= start_date,
        Rental.actual_return_date < end_date
    ).group_by(Product.id).order_by(db.desc('count')).limit(5).all()
    
    product_labels = [p[0] for p in top_products]
    product_rental_counts = [p[1] for p in top_products]
    
    # Top khách hàng thân thiết
    top_customers = db.session.query(
        Customer,
        db.func.count(Rental.id).label('rental_count'),
        db.func.sum(Rental.total_price).label('total_amount')
    ).join(Rental).filter(
        Rental.status == 'returned'
    ).group_by(Customer.id).order_by(db.desc('total_amount')).limit(10).all()
    
    top_customers_list = []
    for customer, rental_count, total_amount in top_customers:
        top_customers_list.append({
            'fullname': customer.fullname,
            'phone': customer.phone,
            'rental_count': rental_count,
            'total_amount': float(total_amount)
        })
    
    return render_template('reports.html',
                         report_type=report_type,
                         period=period,
                         start_date=start_date.strftime('%d/%m/%Y'),
                         end_date=end_date.strftime('%d/%m/%Y'),
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
                     

def get_revenue_by_date_range(start_date, end_date):
    """Tính doanh thu trong khoảng thời gian"""
    total = db.session.query(db.func.sum(Rental.total_price)).filter(
        Rental.status == 'returned',
        Rental.actual_return_date >= start_date,
        Rental.actual_return_date < end_date
    ).scalar()
    return float(total) if total else 0

@app.route('/export-excel')
@login_required
def export_excel():
    """Xuất báo cáo ra file Excel"""
    report_type = request.args.get('report_type', 'month')
    period = request.args.get('period', datetime.now().strftime('%Y-%m'))
    
    # Lấy dữ liệu tương tự như trong reports
    # (Code tương tự, lấy dữ liệu và xuất Excel)
    
    # Tạo DataFrame
    data = []
    rentals = Rental.query.filter(Rental.status == 'returned').all()
    for rental in rentals:
        data.append({
            'Mã đơn': rental.rental_code,
            'Khách hàng': rental.customer.fullname,
            'Sản phẩm': rental.product.name,
            'Số lượng': rental.quantity,
            'Ngày thuê': rental.rental_date.strftime('%d/%m/%Y'),
            'Ngày bắt đầu': rental.start_date.strftime('%d/%m/%Y'),
            'Ngày kết thúc': rental.end_date.strftime('%d/%m/%Y'),
            'Thành tiền': rental.total_price
        })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Doanh thu', index=False)
    
    output.seek(0)
    return send_file(output, 
                     download_name=f'report_{datetime.now().strftime("%Y%m%d")}.xlsx',
                     as_attachment=True)

@app.route('/export-pdf')
@login_required
def export_pdf():
    """Xuất báo cáo ra file PDF"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    
    # Lấy dữ liệu
    rentals = Rental.query.filter(Rental.status == 'returned').all()
    
    # Tạo file PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30)
    styles = getSampleStyleSheet()
    elements = []
    
    # Tiêu đề
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#667eea'))
    elements.append(Paragraph("BÁO CÁO DOANH THU", title_style))
    elements.append(Spacer(1, 20))
    
    # Bảng dữ liệu
    data = [['Mã đơn', 'Khách hàng', 'Sản phẩm', 'Ngày thuê', 'Thành tiền']]
    for rental in rentals[:50]:  # Giới hạn 50 dòng cho PDF
        data.append([
            rental.rental_code,
            rental.customer.fullname,
            rental.product.name,
            rental.rental_date.strftime('%d/%m/%Y'),
            f"{rental.total_price:,.0f} VNĐ"
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
    
    return send_file(buffer, 
                     download_name=f'report_{datetime.now().strftime("%Y%m%d")}.pdf',
                     as_attachment=True, 
                     mimetype='application/pdf')
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
@app.route('/rental-detail/<int:id>')
@login_required
def rental_detail(id):
    rental = Rental.query.get_or_404(id)
    return render_template('rental_detail.html', rental=rental)
@app.route('/delete-rental/<int:id>')
@login_required
def delete_rental(id):
    rental = Rental.query.get_or_404(id)
    
    # Chỉ cho phép xóa đơn đã trả hoặc đã hủy
    if rental.status in ['returned', 'cancelled']:
        # Lấy thông tin để hiển thị flash message
        rental_code = rental.rental_code
        
        db.session.delete(rental)
        db.session.commit()
        flash(f'Đã xóa đơn thuê {rental_code}!', 'success')
    else:
        flash('Không thể xóa đơn đang thuê! Hãy trả hàng hoặc hủy trước.', 'danger')
    
    return redirect(url_for('rentals'))
@app.route('/clear-rental-history')
@login_required
def clear_rental_history():
    # Xóa tất cả đơn đã trả và đã hủy
    returned_count = Rental.query.filter_by(status='returned').count()
    cancelled_count = Rental.query.filter_by(status='cancelled').count()
    
    # Xóa đơn đã trả và đã hủy
    Rental.query.filter(Rental.status.in_(['returned', 'cancelled'])).delete()
    db.session.commit()
    
    total_deleted = returned_count + cancelled_count
    if total_deleted > 0:
        flash(f'Đã xóa {total_deleted} đơn thuê (đã trả: {returned_count}, đã hủy: {cancelled_count})!', 'success')
    else:
        flash('Không có đơn thuê nào để xóa!', 'info')
    
    return redirect(url_for('rentals'))@app.route('/clear-rental-history')
@login_required
def clear_rental_history():
    # Xóa tất cả đơn đã trả và đã hủy
    returned_count = Rental.query.filter_by(status='returned').count()
    cancelled_count = Rental.query.filter_by(status='cancelled').count()
    
    # Xóa đơn đã trả và đã hủy
    Rental.query.filter(Rental.status.in_(['returned', 'cancelled'])).delete()
    db.session.commit()
    
    total_deleted = returned_count + cancelled_count
    if total_deleted > 0:
        flash(f'Đã xóa {total_deleted} đơn thuê (đã trả: {returned_count}, đã hủy: {cancelled_count})!', 'success')
    else:
        flash('Không có đơn thuê nào để xóa!', 'info')
    
    return redirect(url_for('rentals'))@app.route('/clear-rental-history')
@login_required
def clear_rental_history():
    # Xóa tất cả đơn đã trả và đã hủy
    returned_count = Rental.query.filter_by(status='returned').count()
    cancelled_count = Rental.query.filter_by(status='cancelled').count()
    
    # Xóa đơn đã trả và đã hủy
    Rental.query.filter(Rental.status.in_(['returned', 'cancelled'])).delete()
    db.session.commit()
    
    total_deleted = returned_count + cancelled_count
    if total_deleted > 0:
        flash(f'Đã xóa {total_deleted} đơn thuê (đã trả: {returned_count}, đã hủy: {cancelled_count})!', 'success')
    else:
        flash('Không có đơn thuê nào để xóa!', 'info')
    
    return redirect(url_for('rentals'))
@app.route('/cancel-rental/<int:id>')
@login_required
def cancel_rental(id):
    rental = Rental.query.get_or_404(id)
    
    # Chỉ hủy đơn đang thuê
    if rental.status == 'rented':
        rental.status = 'cancelled'
        
        # Trả lại số lượng sản phẩm
        product = Product.query.get(rental.product_id)
        if product:
            product.quantity += rental.quantity
            product.available_quantity += rental.quantity
        
        db.session.commit()
        flash(f'Đã hủy đơn thuê {rental.rental_code}!', 'success')
    else:
        flash('Không thể hủy đơn thuê này!', 'danger')
    
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