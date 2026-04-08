from app import app, db
from models import Admin, Customer, Product, Rental
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

with app.app_context():
    print("Đang thêm dữ liệu mẫu...")
    
    # 1. Xóa dữ liệu cũ
    db.drop_all()
    db.create_all()
    print("Đã reset database")
    
    # 2. Thêm Admin
    admin = Admin(
        username='admin',
        password=generate_password_hash('admin123'),
        email='admin@example.com',
        fullname='Quản trị viên'
    )
    db.session.add(admin)
    print("✓ Đã thêm Admin")
    
    # 3. Thêm Khách hàng
    customers = [
        Customer(fullname='Nguyễn Văn An', phone='0901234567', email='an@gmail.com', address='123 Lê Lợi, Q1, TP.HCM'),
        Customer(fullname='Trần Thị Bình', phone='0912345678', email='binh@gmail.com', address='456 Nguyễn Huệ, Q2, TP.HCM'),
        Customer(fullname='Lê Văn Cường', phone='0923456789', email='cuong@gmail.com', address='789 Võ Văn Kiệt, Q5, TP.HCM'),
        Customer(fullname='Phạm Thị Dung', phone='0934567890', email='dung@gmail.com', address='321 CMT8, Q10, TP.HCM'),
        Customer(fullname='Hoàng Văn Em', phone='0945678901', email='em@gmail.com', address='456 Lê Lai, Q1, TP.HCM'),
    ]
    for c in customers:
        db.session.add(c)
    print(f"✓ Đã thêm {len(customers)} khách hàng")
    
    # 4. Thêm Sản phẩm
    products = [
        Product(name='Đàn Guitar Acoustic', category='Nhạc cụ', description='Đàn guitar acoustic cao cấp, âm thanh ấm', price_per_day=150000, deposit=1000000, quantity=5, available_quantity=5, status='active'),
        Product(name='Micro không dây Shure', category='Thiết bị âm thanh', description='Micro không dây chất lượng chuyên nghiệp', price_per_day=200000, deposit=1500000, quantity=3, available_quantity=3, status='active'),
        Product(name='Loa kéo di động', category='Thiết bị âm thanh', description='Loa kéo công suất lớn, pin trâu', price_per_day=300000, deposit=2000000, quantity=2, available_quantity=2, status='active'),
        Product(name='Đèn LED sân khấu', category='Ánh sáng', description='Đèn LED màu, hiệu ứng đẹp', price_per_day=250000, deposit=1200000, quantity=10, available_quantity=10, status='active'),
        Product(name='Trống Cajon', category='Nhạc cụ', description='Trống cajon gỗ cao cấp', price_per_day=120000, deposit=800000, quantity=4, available_quantity=4, status='active'),
        Product(name='Bàn phím điện tử', category='Nhạc cụ', description='Đàn keyboard 61 phím, nhiều tiếng đàn', price_per_day=180000, deposit=1500000, quantity=3, available_quantity=3, status='active'),
        Product(name='Amply karaoke', category='Thiết bị âm thanh', description='Amply 100W, công suất mạnh', price_per_day=250000, deposit=2000000, quantity=3, available_quantity=3, status='active'),
        Product(name='Chân micro', category='Phụ kiện', description='Chân micro chuyên nghiệp', price_per_day=50000, deposit=200000, quantity=10, available_quantity=10, status='active'),
    ]
    for p in products:
        db.session.add(p)
    print(f"✓ Đã thêm {len(products)} sản phẩm")
    
    db.session.commit()
    
    # 5. Thêm Đơn thuê mẫu
    customers = Customer.query.all()
    products = Product.query.all()
    
    rentals = [
        Rental(
            rental_code=f'HD{datetime.now().strftime("%Y%m%d")}001',
            customer_id=customers[0].id,
            product_id=products[0].id,
            quantity=1,
            start_date=datetime.now() - timedelta(days=5),
            end_date=datetime.now() + timedelta(days=2),
            price_per_day=products[0].price_per_day,
            deposit_amount=products[0].deposit,
            total_price=products[0].price_per_day * 7,
            status='rented'
        ),
        Rental(
            rental_code=f'HD{datetime.now().strftime("%Y%m%d")}002',
            customer_id=customers[1].id,
            product_id=products[1].id,
            quantity=2,
            start_date=datetime.now() - timedelta(days=10),
            end_date=datetime.now() - timedelta(days=3),
            actual_return_date=datetime.now() - timedelta(days=3),
            price_per_day=products[1].price_per_day,
            deposit_amount=products[1].deposit * 2,
            total_price=products[1].price_per_day * 7 * 2,
            status='returned'
        ),
        Rental(
            rental_code=f'HD{datetime.now().strftime("%Y%m%d")}003',
            customer_id=customers[2].id,
            product_id=products[2].id,
            quantity=1,
            start_date=datetime.now() - timedelta(days=2),
            end_date=datetime.now() + timedelta(days=5),
            price_per_day=products[2].price_per_day,
            deposit_amount=products[2].deposit,
            total_price=products[2].price_per_day * 7,
            status='rented'
        ),
    ]
    
    for r in rentals:
        # Cập nhật số lượng sản phẩm
        product = Product.query.get(r.product_id)
        if product:
            product.available_quantity -= r.quantity
        db.session.add(r)
    
    db.session.commit()
    print(f"✓ Đã thêm {len(rentals)} đơn thuê mẫu")
    
    print("\n" + "="*50)
    print("✅ THÊM DỮ LIỆU MẪU THÀNH CÔNG!")
    print("="*50)
    print("Thông tin đăng nhập:")
    print("  Username: admin")
    print("  Password: admin123")
    print("="*50)
    print(f"Khách hàng: {Customer.query.count()}")
    print(f"Sản phẩm: {Product.query.count()}")
    print(f"Đơn thuê: {Rental.query.count()}")
    print("="*50)