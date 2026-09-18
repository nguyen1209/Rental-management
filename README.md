# Rental Management – TPBD Phương Lan

Ứng dụng Flask quản lý sản phẩm, khách hàng, tồn kho, đơn thuê và báo cáo doanh thu.

## Chạy bằng Docker

1. Sao chép `.env.example` thành `.env`.
2. Đặt `SECRET_KEY`, `ADMIN_PASSWORD` và `POSTGRES_PASSWORD` thành các giá trị mạnh.
3. Chạy `docker compose up --build -d`.
4. Mở trang khách tại `http://127.0.0.1:8000/rent` và trang quản trị tại
   `http://127.0.0.1:8000/admin`.

Docker sử dụng PostgreSQL và lưu dữ liệu trong volume `postgres_data`; ảnh tải lên
được lưu trong `uploads/`. Lần chạy đầu tiên sẽ tạo một database trống và tài khoản
admin từ `.env`.

Kiểm tra PostgreSQL:

```bash
docker compose ps
docker compose exec postgres psql -U rental -d rental -c "SELECT count(*) FROM product;"
```

## Chạy cục bộ

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = 'development-secret'
$env:ADMIN_PASSWORD = 'change-this-password'
python app.py
```

Khi thay đổi cấu trúc database, tạo và áp dụng migration bằng:

```powershell
flask --app app db migrate -m "Mô tả thay đổi"
flask --app app db upgrade
```

Nếu không đặt biến môi trường khi chạy cục bộ, tài khoản khởi tạo là
`admin` / `admin123`; không sử dụng giá trị này khi triển khai thật.

## Kiểm thử

```powershell
python test.py
```

Bộ test sử dụng database tạm, không thay đổi `instance/rental.db`.

## Sao lưu và giám sát

Chạy backup hằng ngày trên máy chủ (ví dụ bằng cron lúc 02:00):

```bash
0 2 * * * cd /home/thanhnguyen12092003/Rental-management && sh ./scripts/backup.sh >> /var/log/rental-backup.log 2>&1
```

Mỗi bản backup gồm PostgreSQL và toàn bộ ảnh tải lên; mặc định giữ 14 ngày. Kiểm tra
`/health` để giám sát kết nối database và dung lượng đĩa. Có thể đặt `ANALYTICS_ID`
trong `.env` để bật Google Analytics và `MIN_FREE_DISK_MB` để đổi ngưỡng cảnh báo.
