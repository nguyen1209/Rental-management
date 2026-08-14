# Cloudflare cho TPBD Phương Lan

## Kiến trúc đề xuất

Cloudflare Tunnel chuyển lưu lượng từ domain công khai đến service Flask trong
Docker qua địa chỉ nội bộ `http://web:8000`. Server không cần mở cổng 8000 ra
Internet. Service Tunnel được đặt trong profile riêng nên cấu hình hiện tại vẫn
chạy bình thường nếu chưa có token.

## 1. Tạo Tunnel

1. Mở Cloudflare Dashboard.
2. Chọn **Networking > Tunnels > Create Tunnel**.
3. Chọn connector **Cloudflared** và đặt tên `phuong-lan-production`.
4. Chọn môi trường Docker và sao chép token sau `--token`.
5. Thêm token vào file `.env` trên server:

   ```env
   CLOUDFLARE_TUNNEL_TOKEN=token-thật-từ-cloudflare
   ```

Không đưa token thật vào GitHub hoặc gửi qua tin nhắn.

## 2. Tạo hostname công khai

Trong Tunnel, chọn **Routes > Add route > Published application**:

- Hostname: `trangphucbieudienphuonglan.io.vn`
- Service type: `HTTP`
- Service URL: `web:8000`

Cloudflare sẽ tạo bản ghi DNS trỏ domain vào Tunnel. Xóa hoặc tắt proxy bản ghi
A/AAAA cũ sau khi Tunnel đã báo **Healthy** để tránh lộ IP origin.

## 3. Khởi động

Trên server, tại thư mục dự án:

```bash
docker compose --profile tunnel up -d
docker compose ps
docker compose logs --tail=100 cloudflared
```

Để kiểm tra:

```bash
curl --fail https://trangphucbieudienphuonglan.io.vn/health
```

Kết quả đúng là JSON có trạng thái `ok`.

## 4. Thiết lập bảo mật

- SSL/TLS encryption mode: **Full (strict)** nếu vẫn dùng HTTPS tới nginx origin.
  Khi Tunnel trỏ thẳng tới `web:8000`, kết nối từ `cloudflared` tới Flask nằm
  trong Docker network và dùng HTTP nội bộ.
- Bật **Always Use HTTPS**.
- Tạo Cache Rule với hành động **Bypass cache** cho các đường dẫn:
  `/admin*`, `/login*`, `/logout*`, `/customer*`, `/checkout*`.
- Có thể tạo Cloudflare Access application bảo vệ `/admin*` và `/login*` bằng
  email OTP. Không bảo vệ toàn domain vì khách hàng vẫn cần xem cửa hàng.

## 5. Lưu ý về deploy

Cloudflare Tunnel chỉ phục vụ lưu lượng website. GitHub Actions vẫn cần SSH key
hợp lệ để pull code và chạy Docker Compose trên server.
