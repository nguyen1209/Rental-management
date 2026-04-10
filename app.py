from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import calendar
import secrets
import os
import json
from sqlalchemy import func, desc

from models import db, Admin, Customer, Product, Rental, RentalDetail

app = Flask(__name__)

# Cấu hình
app.config['SECRET_KEY'] = 'your-secret-key-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rental.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cấu hình upload
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# ==================== TRANG CHỦ & ĐĂNG NHẬP ====================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

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
    active_rentals = Rental.query.filter_by(status='rented').count()
    
    return render_template('dashboard.html', 
                         total_customers=total_customers,
                         total_products=total_products,
                         total_rentals=total_rentals,
                         active_rentals=active_rentals)

# ==================== QUẢN LÝ KHÁCH HÀNG ====================
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

# ==================== QUẢN LÝ SẢN PHẨM ====================
@app.route('/products')
@login_required
def products():
    all_products = Product.query.all()
    return render_template('products.html', products=all_products)

@app.route('/add-product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        image_url = request.form.get('image_url', '')
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
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
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                if product.image_url and product.image_url.startswith('/static/uploads/'):
                    old_filepath = product.image_url.replace('/static/', 'static/')
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                product.image_url = url_for('static', filename=f'uploads/{filename}')
        
        image_url_input = request.form.get('image_url', '')
        if image_url_input:
            product.image_url = image_url_input
        
        db.session.commit()
        flash('Cập nhật sản phẩm thành công!', 'success')
        return redirect(url_for('products'))
    
    return render_template('edit_product.html', product=product)

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

# ==================== QUẢN LÝ ĐƠN THUÊ ====================
@app.route('/rentals')
@login_required
def rentals():
    all_rentals = Rental.query.order_by(Rental.rental_date.desc()).all()
    return render_template('rentals.html', rentals=all_rentals)

@app.route('/add-rental', methods=['GET', 'POST'])
@login_required
def add_rental():
    if request.method == 'POST':
        customer_id = int(request.form['customer_id'])
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
        
        days = (end_date - start_date).days
        if days <= 0:
            flash('Ngày kết thúc phải sau ngày bắt đầu!', 'danger')
            return redirect(url_for('add_rental'))
        
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        
        if not product_ids:
            flash('Vui lòng chọn ít nhất 1 sản phẩm!', 'danger')
            return redirect(url_for('add_rental'))
        
        rental_code = f"HD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        rental = Rental(
            rental_code=rental_code,
            customer_id=customer_id,
            start_date=start_date,
            end_date=end_date,
            status='rented'
        )
        db.session.add(rental)
        db.session.flush()
        
        total_amount = 0
        
        for i in range(len(product_ids)):
            product_id = int(product_ids[i])
            quantity = int(quantities[i])
            
            if quantity <= 0:
                continue
                
            product = Product.query.get(product_id)
            if not product:
                continue
            
            if quantity > product.available_quantity:
                flash(f'Sản phẩm {product.name} chỉ còn {product.available_quantity}!', 'danger')
                db.session.rollback()
                return redirect(url_for('add_rental'))
            
            subtotal = product.price_per_day * days * quantity
            total_amount += subtotal
            
            detail = RentalDetail(
                rental_id=rental.id,
                product_id=product_id,
                quantity=quantity,
                price_per_day=product.price_per_day,
                days=days,
                subtotal=subtotal
            )
            db.session.add(detail)
            
            product.available_quantity -= quantity
        
        rental.total_amount = total_amount
        db.session.commit()
        
        flash(f'Tạo đơn thuê thành công! Mã: {rental_code} - Tổng tiền: {total_amount:,.0f}đ', 'success')
        return redirect(url_for('rentals'))
    
    customers = Customer.query.all()
    products = Product.query.filter(Product.available_quantity > 0).all()
    return render_template('add_rental.html', customers=customers, products=products)

@app.route('/return-rental/<int:id>')
@login_required
def return_rental(id):
    rental = Rental.query.get_or_404(id)
    rental.status = 'returned'
    rental.actual_return_date = datetime.now()
    
    for detail in rental.details:
        product = Product.query.get(detail.product_id)
        if product:
            product.available_quantity += detail.quantity
            product.quantity += detail.quantity
    
    db.session.commit()
    flash('Đã xác nhận trả hàng!', 'success')
    return redirect(url_for('rentals'))

@app.route('/cancel-rental/<int:id>')
@login_required
def cancel_rental(id):
    rental = Rental.query.get_or_404(id)
    
    if rental.status == 'rented':
        rental.status = 'cancelled'
        
        for detail in rental.details:
            product = Product.query.get(detail.product_id)
            if product:
                product.available_quantity += detail.quantity
                product.quantity += detail.quantity
        
        db.session.commit()
        flash(f'Đã hủy đơn thuê {rental.rental_code}!', 'success')
    else:
        flash('Không thể hủy đơn này!', 'danger')
    
    return redirect(url_for('rentals'))

@app.route('/delete-rental/<int:id>')
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
    # Lấy tham số từ request
    report_type = request.args.get('report_type', 'month')
    period = request.args.get('period', datetime.now().strftime('%Y-%m'))
    
    today = datetime.now()
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
        end_date = datetime(year, 12, 31)
        
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
    
    return render_template('reports.html',
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
    return send_file(output, 
                     download_name=f'report_{datetime.now().strftime("%Y%m%d")}.xlsx',
                     as_attachment=True)

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
    
    return send_file(buffer, 
                     download_name=f'report_{datetime.now().strftime("%Y%m%d")}.pdf',
                     as_attachment=True, 
                     mimetype='application/pdf')

# ==================== KHỞI TẠO DATABASE ====================
def init_db():
    with app.app_context():
        db.create_all()
        
        if not Admin.query.first():
            admin = Admin(
                username='admin',
                password=generate_password_hash('admin123'),
                email='admin@example.com',
                fullname='Administrator'
            )
            db.session.add(admin)
        
        
        db.session.commit()
        print("Database created successfully!")
        print("Admin account: admin / admin123")

if __name__ == '__main__':
    init_db()
    app.run(debug=True)