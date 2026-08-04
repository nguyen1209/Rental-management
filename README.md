# Rental Management – TPBD Phương Lan

Ứng dụng Flask quản lý sản phẩm, khách hàng, tồn kho, đơn thuê và báo cáo doanh thu.

## Chạy bằng Docker

1. Sao chép `.env.example` thành `.env`.
2. Đặt `SECRET_KEY` ngẫu nhiên dài và mật khẩu quản trị mạnh.
3. Chạy `docker compose up --build -d`.
4. Mở trang khách tại `http://127.0.0.1:8000/rent` và trang quản trị tại
   `http://127.0.0.1:8000/admin`.

Dữ liệu được lưu trong `data/`; ảnh tải lên được lưu trong `uploads/`.

## Chạy cục bộ

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = 'development-secret'
$env:ADMIN_PASSWORD = 'change-this-password'
python app.py
```

Nếu không đặt biến môi trường khi chạy cục bộ, tài khoản khởi tạo là
`admin` / `admin123`; không sử dụng giá trị này khi triển khai thật.

## Kiểm thử

```powershell
python test.py
```

Bộ test sử dụng database tạm, không thay đổi `instance/rental.db`.
