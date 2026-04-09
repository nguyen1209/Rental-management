from app import app, db
from models import Rental
from datetime import datetime

with app.app_context():
    print("=== TEST HÀM TÍNH DOANH THU ===\n")
    
    # Test với khoảng thời gian cụ thể
    start = datetime(2026, 4, 1)
    end = datetime(2026, 5, 1)
    
    result = db.session.query(db.func.sum(Rental.total_price)).filter(
        Rental.status == 'returned',
        Rental.actual_return_date >= start,
        Rental.actual_return_date < end
    ).scalar()
    
    print(f"Doanh thu tháng 4: {result}")
    print(f"Kiểu dữ liệu: {type(result)}")
    
    # Kiểm tra tất cả đơn returned
    all_returned = Rental.query.filter_by(status='returned').all()
    print(f"\nSố đơn returned: {len(all_returned)}")
    for r in all_returned:
        print(f"  - {r.rental_code}: {r.total_price}đ, ngày trả: {r.actual_return_date}")