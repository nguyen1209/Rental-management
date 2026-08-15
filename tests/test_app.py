import os
import io
import tempfile
import unittest

TEST_DB = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
TEST_DB.close()
os.environ['DATABASE_URL'] = f"sqlite:///{TEST_DB.name.replace(os.sep, '/')}"
os.environ['SECRET_KEY'] = 'test-secret-key'

from app import app  # noqa: E402
from models import Admin, Product, Rental, RentalDetail, db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


class RentalAppTestCase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(TEST_DB.name)
        except OSError:
            pass

    def setUp(self):
        app.config.update(TESTING=True)
        with app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(Admin(username='admin', password=generate_password_hash('admin123'),
                                 fullname='Administrator'))
            db.session.commit()
        self.client = app.test_client()

    def csrf(self, path='/login'):
        self.client.get(path)
        with self.client.session_transaction() as session:
            return session['_csrf_token']

    def login_admin(self):
        response = self.client.post('/login', data={
            '_csrf_token': self.csrf(), 'username': 'admin', 'password': 'admin123'})
        self.assertEqual(response.status_code, 302)

    def create_product(self, quantity=3):
        with app.app_context():
            product = Product(name='Áo dài đỏ', category='Áo dài', price_per_day=100000,
                              quantity=quantity, available_quantity=quantity, status='active')
            db.session.add(product)
            db.session.commit()
            return product.id

    def test_public_pages_and_csrf_protection(self):
        for path in ('/health', '/rent', '/customer/login', '/customer/register', '/login'):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get('/checkout').status_code, 302)
        self.assertIn('/customer/login?next=', self.client.get('/checkout').location)
        self.assertEqual(self.client.post('/customer/register', data={}).status_code, 400)
        self.assertEqual(self.client.get('/dashboard').status_code, 302)

    def test_public_seo_endpoints_and_metadata(self):
        robots = self.client.get('/robots.txt')
        self.assertEqual(robots.status_code, 200)
        self.assertIn(b'Sitemap: https://trangphucbieudienphuonglan.io.vn/sitemap.xml', robots.data)
        sitemap = self.client.get('/sitemap.xml')
        self.assertEqual(sitemap.status_code, 200)
        self.assertIn(b'<loc>https://trangphucbieudienphuonglan.io.vn/rent</loc>', sitemap.data)
        store = self.client.get('/rent')
        self.assertIn(b'<meta name="description"', store.data)
        self.assertIn(b'<link rel="canonical"', store.data)
        self.assertIn(b'application/ld+json', store.data)
        self.assertIn(b'"areaServed"', store.data)
        self.assertIn('Đồng Tháp'.encode(), store.data)
        self.assertIn('An Giang'.encode(), store.data)
        self.assertIn('Cần Thơ'.encode(), store.data)
        self.assertIn('Vĩnh Long'.encode(), store.data)
        self.assertIn(b'<meta name="robots" content="index, follow">', store.data)
        login = self.client.get('/login')
        self.assertIn(b'<meta name="robots" content="noindex, nofollow">', login.data)

    def test_customer_register_order_and_history(self):
        product_id = self.create_product()
        response = self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Nguyễn An',
            'phone': '0900000001', 'email': 'an@example.com', 'password': 'secret1'})
        self.assertEqual(response.status_code, 302)
        response = self.client.post('/checkout', data={
            '_csrf_token': self.csrf('/checkout'), 'fullname': 'Nguyễn An',
            'phone': '0900000001', 'email': 'an@example.com', 'address': 'Đồng Tháp',
            'start_date': '2026-08-10', 'end_date': '2026-08-12',
            'product_id[]': [str(product_id)], 'quantity[]': ['2']})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = Rental.query.one()
            self.assertEqual(rental.status, 'pending')
            self.assertEqual(rental.total_amount, 400000)
            self.assertEqual(db.session.get(Product, product_id).available_quantity, 1)
        self.assertEqual(self.client.get('/customer/orders').status_code, 200)

    def test_customer_checkout_supports_dates_per_item(self):
        first_product_id = self.create_product(quantity=2)
        second_product_id = self.create_product(quantity=2)
        self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Khách Chọn Lịch',
            'phone': '0900000005', 'email': 'lich@example.com', 'password': 'secret1'})
        response = self.client.post('/checkout', data={
            '_csrf_token': self.csrf('/checkout'), 'fullname': 'Khách Chọn Lịch',
            'phone': '0900000005', 'start_date': '2026-08-10', 'end_date': '2026-08-16',
            'product_id[]': [str(first_product_id), str(second_product_id)],
            'quantity[]': ['1', '1'],
            'item_start_date[]': ['2026-08-10', '2026-08-12'],
            'item_end_date[]': ['2026-08-12', '2026-08-16']})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = Rental.query.one()
            details = {detail.product_id: detail for detail in rental.details}
            self.assertEqual(rental.total_amount, 600000)
            self.assertEqual(details[first_product_id].days, 2)
            self.assertEqual(details[second_product_id].days, 4)
            self.assertEqual(details[first_product_id].start_date.strftime('%Y-%m-%d'), '2026-08-10')
            self.assertEqual(details[second_product_id].end_date.strftime('%Y-%m-%d'), '2026-08-16')

    def test_bank_transfer_order_can_be_confirmed_by_admin(self):
        product_id = self.create_product()
        self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Khách Chuyển Khoản',
            'phone': '0900000006', 'email': 'bank@example.com', 'password': 'secret1'})
        response = self.client.post('/checkout', data={
            '_csrf_token': self.csrf('/checkout'), 'fullname': 'Khách Chuyển Khoản',
            'phone': '0900000006', 'start_date': '2026-08-10', 'end_date': '2026-08-12',
            'payment_method': 'bank_transfer',
            'product_id[]': [str(product_id)], 'quantity[]': ['1']})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = Rental.query.one()
            rental_id = rental.id
            self.assertEqual(rental.payment_method, 'bank_transfer')
            self.assertEqual(rental.payment_status, 'pending_confirmation')

        bank_config = {key: app.config[key] for key in ('BANK_CODE', 'BANK_ACCOUNT', 'BANK_ACCOUNT_NAME')}
        app.config.update(BANK_CODE='', BANK_ACCOUNT='', BANK_ACCOUNT_NAME='')
        history = self.client.get('/customer/orders')
        app.config.update(bank_config)
        self.assertIn(b'0396970191', history.data)
        self.assertIn(b'img.vietqr.io', history.data)
        self.assertIn(b'class="order-active"', history.data)

        self.login_admin()
        response = self.client.post(f'/rentals/{rental_id}/confirm-payment', data={
            '_csrf_token': self.csrf('/rentals')})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = db.session.get(Rental, rental_id)
            self.assertEqual(rental.payment_status, 'paid')
            self.assertIsNotNone(rental.paid_at)

    def test_customer_can_upload_bank_transfer_receipt(self):
        product_id = self.create_product()
        self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Khách Gửi Biên Lai',
            'phone': '0900000010', 'email': 'receipt@example.com', 'password': 'secret1'})
        self.client.post('/checkout', data={
            '_csrf_token': self.csrf('/checkout'), 'fullname': 'Khách Gửi Biên Lai',
            'phone': '0900000010', 'start_date': '2026-08-10', 'end_date': '2026-08-12',
            'payment_method': 'bank_transfer',
            'product_id[]': [str(product_id)], 'quantity[]': ['1']})
        with app.app_context():
            rental_id = Rental.query.one().id
        with tempfile.TemporaryDirectory() as upload_folder:
            previous_upload_folder = app.config['UPLOAD_FOLDER']
            app.config['UPLOAD_FOLDER'] = upload_folder
            response = self.client.post(f'/customer/orders/{rental_id}/payment-proof', data={
                '_csrf_token': self.csrf('/customer/orders'),
                'payment_receipt': (io.BytesIO(b'fake-image'), 'receipt.png')},
                content_type='multipart/form-data')
            app.config['UPLOAD_FOLDER'] = previous_upload_folder
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = db.session.get(Rental, rental_id)
            self.assertEqual(rental.payment_status, 'customer_submitted')
            self.assertIn('/payment_receipts/receipt_', rental.payment_receipt_url)
            self.assertIsNotNone(rental.payment_submitted_at)

    def test_admin_order_lifecycle_restores_inventory(self):
        product_id = self.create_product(quantity=2)
        self.login_admin()
        response = self.client.post('/add-rental', data={
            '_csrf_token': self.csrf('/add-rental'), 'customer_mode': 'guest',
            'guest_name': 'Khách lẻ', 'guest_phone': '0900000002',
            'start_date': '2026-08-10', 'end_date': '2026-08-13',
            'product_id[]': [str(product_id)], 'quantity[]': ['1'],
            'item_start_date[]': [''], 'item_end_date[]': ['']})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental_id = Rental.query.one().id
            self.assertEqual(db.session.get(Product, product_id).available_quantity, 1)
        token = self.csrf('/rentals')
        self.assertEqual(self.client.post(f'/prepare-rental/{rental_id}', data={'_csrf_token': token}).status_code, 302)
        self.assertEqual(self.client.post(f'/return-rental/{rental_id}', data={'_csrf_token': token}).status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(Rental, rental_id).status, 'returned')
            self.assertEqual(db.session.get(Product, product_id).available_quantity, 2)

    def test_mutating_routes_reject_get(self):
        product_id = self.create_product()
        self.login_admin()
        for path in (f'/delete-product/{product_id}', '/delete-customer/999',
                     '/delete-category/999', '/prepare-rental/999', '/return-rental/999',
                     '/cancel-rental/999', '/delete-rental/999',
                     '/rentals/999/confirm-payment'):
            self.assertEqual(self.client.get(path).status_code, 405, path)

    def test_admin_pages_render(self):
        self.create_product()
        self.login_admin()
        for path in ('/dashboard', '/customers', '/products', '/categories', '/add-product',
                     '/rentals', '/add-rental', '/reports'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_admin_can_upload_product_photo_from_phone_camera(self):
        self.login_admin()
        page = self.client.get('/add-product')
        self.assertIn(b'name="camera_image"', page.data)
        self.assertIn(b'capture="environment"', page.data)
        with tempfile.TemporaryDirectory() as upload_folder:
            previous_upload_folder = app.config['UPLOAD_FOLDER']
            app.config['UPLOAD_FOLDER'] = upload_folder
            response = self.client.post('/add-product', data={
                '_csrf_token': self.csrf('/add-product'), 'name': 'Ảnh từ điện thoại',
                'category': 'Quần áo', 'price_per_day': '100000', 'deposit': '0',
                'quantity': '1', 'gender': 'unisex', 'sizes': ['M'],
                'image_url': 'https://example.com/old.jpg',
                'camera_image': (io.BytesIO(b'phone-photo'), 'camera.jpg')},
                content_type='multipart/form-data')
            app.config['UPLOAD_FOLDER'] = previous_upload_folder
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            product = Product.query.filter_by(name='Ảnh từ điện thoại').one()
            self.assertTrue(product.image_url.startswith('/static/uploads/product_'))
            self.assertNotEqual(product.image_url, 'https://example.com/old.jpg')

    def test_gender_size_filter_and_selected_size_are_saved(self):
        with app.app_context():
            product = Product(name='Váy biểu diễn nữ', category='Váy', gender='female',
                              sizes='|S|M|', price_per_day=150000, quantity=2,
                              available_quantity=2, status='active')
            db.session.add(product)
            db.session.commit()
            product_id = product.id

        filtered = self.client.get('/rent?gender=female&size=M')
        self.assertIn('Váy biểu diễn nữ'.encode(), filtered.data)
        self.assertNotIn('option value="XL" selected'.encode(), filtered.data)

        self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Khách chọn size',
            'phone': '0900000999', 'email': 'size@example.com', 'password': 'secret1'})
        response = self.client.post('/checkout', data={
            '_csrf_token': self.csrf('/checkout'), 'fullname': 'Khách chọn size',
            'phone': '0900000999', 'start_date': '2026-09-01', 'end_date': '2026-09-03',
            'product_id[]': [str(product_id)], 'quantity[]': ['1'], 'size[]': ['M']})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(RentalDetail.query.one().selected_size, 'M')

    def test_customer_page_does_not_use_admin_layout_when_both_sessions_exist(self):
        self.login_admin()
        self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Khách Hai Vai Trò',
            'phone': '0900000007', 'email': 'roles@example.com', 'password': 'secret1'})

        customer_page = self.client.get('/customer/orders')
        self.assertEqual(customer_page.status_code, 200)
        self.assertIn(b'class="store-body"', customer_page.data)
        self.assertNotIn(b'class="admin-shell"', customer_page.data)

        admin_page = self.client.get('/dashboard')
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn(b'class="admin-shell"', admin_page.data)

    def test_completed_customer_orders_use_compact_layout(self):
        product_id = self.create_product()
        self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Khách Hoàn Tất',
            'phone': '0900000008', 'email': 'done@example.com', 'password': 'secret1'})
        self.client.post('/checkout', data={
            '_csrf_token': self.csrf('/checkout'), 'fullname': 'Khách Hoàn Tất',
            'phone': '0900000008', 'start_date': '2026-08-10', 'end_date': '2026-08-12',
            'product_id[]': [str(product_id)], 'quantity[]': ['1']})
        with app.app_context():
            rental = Rental.query.one()
            rental.status = 'returned'
            db.session.commit()

        history = self.client.get('/customer/orders')
        self.assertIn(b'class="order-compact"', history.data)
        self.assertNotIn(b'class="order-active"', history.data)

    def test_reports_validate_period_and_exports_work(self):
        self.login_admin()
        response = self.client.get('/reports?report_type=month&period=not-a-month')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/reports?', response.location)
        excel = self.client.get('/export-excel')
        pdf = self.client.get('/export-pdf')
        self.assertEqual(excel.status_code, 200)
        self.assertIn('spreadsheetml', excel.content_type)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.content_type, 'application/pdf')
        self.assertTrue(pdf.data.startswith(b'%PDF'))


    def test_admin_invoice_renders(self):
        product_id = self.create_product(quantity=2)
        self.login_admin()
        self.client.post('/add-rental', data={
            '_csrf_token': self.csrf('/add-rental'), 'customer_mode': 'guest',
            'guest_name': 'Khách In Đơn', 'guest_phone': '0900000003',
            'start_date': '2026-08-10', 'end_date': '2026-08-13',
            'product_id[]': [str(product_id)], 'quantity[]': ['1'],
            'item_start_date[]': [''], 'item_end_date[]': ['']})
        with app.app_context():
            rental_id = Rental.query.one().id
        response = self.client.get(f'/rentals/{rental_id}/invoice')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'H\xc3\x93A \xc4\x90\xc6\xa0N CHO THU\xc3\x8a', response.data)

    def test_customer_rent_date_range_filtering(self):
        product_id = self.create_product(quantity=2)
        self.login_admin()
        # Đặt 2 áo dài từ 2026-08-10 đến 2026-08-15
        self.client.post('/add-rental', data={
            '_csrf_token': self.csrf('/add-rental'), 'customer_mode': 'guest',
            'guest_name': 'Khách Đặt Trước', 'guest_phone': '0900000004',
            'start_date': '2026-08-10', 'end_date': '2026-08-15',
            'product_id[]': [str(product_id)], 'quantity[]': ['2'],
            'item_start_date[]': [''], 'item_end_date[]': ['']})

        # Tìm khoảng ngày đè lịch (2026-08-12 đến 2026-08-14) -> số lượng khả dụng = 0 (bị ẩn)
        resp_overlap = self.client.get('/rent?start_date=2026-08-12&end_date=2026-08-14')
        self.assertEqual(resp_overlap.status_code, 200)
        self.assertNotIn('Áo dài đỏ', resp_overlap.data.decode('utf-8'))

        # Tìm khoảng ngày không đè lịch (2026-08-20 đến 2026-08-25) -> số lượng khả dụng = 2 (hiển thị)
        resp_free = self.client.get('/rent?start_date=2026-08-20&end_date=2026-08-25')
        self.assertEqual(resp_free.status_code, 200)
        self.assertIn('Áo dài đỏ', resp_free.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
