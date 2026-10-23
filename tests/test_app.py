import os
import io
import tempfile
import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

TEST_DB = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
TEST_DB.close()
os.environ['DATABASE_URL'] = f"sqlite:///{TEST_DB.name.replace(os.sep, '/')}"
os.environ['SECRET_KEY'] = 'test-secret-key'

from app import app  # noqa: E402
from models import Admin, Category, Customer, Product, Rental, RentalDetail, db  # noqa: E402
from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402


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
        response = self.client.post('/admin/login', data={
            '_csrf_token': self.csrf('/admin/login'), 'username': 'admin', 'password': 'admin123'})
        self.assertEqual(response.status_code, 302)

    def test_customer_can_reset_password_with_single_use_email_token(self):
        with app.app_context():
            customer = Customer(fullname='Reset Customer', phone='0900000088',
                                email='reset@example.com',
                                password_hash=generate_password_hash('old-password'))
            db.session.add(customer)
            db.session.commit()

        with patch('app.send_password_reset_email') as send_email:
            response = self.client.post('/customer/forgot-password', data={
                '_csrf_token': self.csrf('/customer/forgot-password'),
                'email': 'RESET@example.com'})
        self.assertEqual(response.status_code, 302)
        send_email.assert_called_once()
        reset_url = send_email.call_args.args[1]
        token = parse_qs(urlparse(reset_url).query)['token'][0]

        reset_path = '/customer/reset-password'
        response = self.client.post(reset_path, data={
            '_csrf_token': self.csrf(reset_path),
            'token': token,
            'password': 'new-password-123', 'password_confirm': 'new-password-123'})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            customer = Customer.query.filter_by(phone='0900000088').one()
            self.assertTrue(check_password_hash(customer.password_hash, 'new-password-123'))
            self.assertIsNone(customer.password_reset_token_hash)
            self.assertIsNone(customer.password_reset_expires_at)

        self.assertEqual(self.client.get(reset_path).status_code, 302)

    def test_forgot_password_response_does_not_reveal_unknown_email(self):
        with patch('app.send_password_reset_email') as send_email:
            response = self.client.post('/customer/forgot-password', data={
                '_csrf_token': self.csrf('/customer/forgot-password'),
                'email': 'unknown@example.com'})
        self.assertEqual(response.status_code, 302)
        send_email.assert_not_called()

    def test_admin_login_has_its_own_password_reset_flow(self):
        with app.app_context():
            admin = Admin.query.filter_by(username='admin').one()
            admin.email = 'owner@example.com'
            db.session.commit()

        with patch('app.send_password_reset_email') as send_email:
            response = self.client.post('/admin/forgot-password', data={
                '_csrf_token': self.csrf('/admin/forgot-password'),
                'email': 'OWNER@example.com'})
        self.assertEqual(response.status_code, 302)
        send_email.assert_called_once()
        reset_url = send_email.call_args.args[1]
        token = parse_qs(urlparse(reset_url).query)['token'][0]

        response = self.client.post('/admin/reset-password', data={
            '_csrf_token': self.csrf('/admin/reset-password'), 'token': token,
            'password': 'new-admin-password', 'password_confirm': 'new-admin-password'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/admin/login')
        with app.app_context():
            admin = Admin.query.filter_by(username='admin').one()
            self.assertTrue(check_password_hash(admin.password, 'new-admin-password'))
            self.assertIsNone(admin.password_reset_token_hash)

    def create_product(self, quantity=3):
        with app.app_context():
            product = Product(name='Áo dài đỏ', category='Áo dài', price_per_day=100000,
                              quantity=quantity, available_quantity=quantity, status='active')
            db.session.add(product)
            db.session.commit()
            return product.id

    def test_admin_can_open_product_edit_form_with_category_options(self):
        product_id = self.create_product()
        with app.app_context():
            root = Category(name='Trang phục', sort_order=0)
            root.children.append(Category(name='Áo dài', sort_order=0))
            db.session.add(root)
            db.session.commit()

        self.login_admin()
        response = self.client.get(f'/edit-product/{product_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="category"', response.data)
        self.assertIn('Áo dài'.encode(), response.data)
        self.assertIn('value="Áo dài"'.encode(), response.data)

    def test_add_product_validation_keeps_submitted_values(self):
        self.login_admin()
        response = self.client.post('/add-product', data={
            '_csrf_token': self.csrf('/add-product'),
            'name': 'Áo thử nhập thiếu giá', 'category': 'Quần áo',
            'description': 'Mô tả cần giữ lại', 'price_per_day': '', 'deposit': '25000',
            'variant_gender[]': ['male'], 'variant_size[]': ['M'],
            'variant_quantity[]': ['2'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('Áo thử nhập thiếu giá'.encode(), response.data)
        self.assertIn('Mô tả cần giữ lại'.encode(), response.data)
        self.assertIn(b'name="price_per_day" class="form-control" value=""', response.data)
        self.assertIn(b'name="variant_quantity[]" class="form-control" min="0" value="2"', response.data)
        with app.app_context():
            self.assertEqual(Product.query.count(), 0)

    def test_edit_product_validation_keeps_submitted_values(self):
        product_id = self.create_product(quantity=2)
        self.login_admin()
        response = self.client.post(f'/edit-product/{product_id}', data={
            '_csrf_token': self.csrf(f'/edit-product/{product_id}'),
            'name': 'Tên mới cần giữ', 'category': 'Danh mục mới',
            'description': 'Mô tả mới cần giữ', 'price_per_day': '',
            'deposit': '35000', 'variant_gender[]': ['male'],
            'variant_size[]': ['M'], 'variant_quantity[]': ['1'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('Tên mới cần giữ'.encode(), response.data)
        self.assertIn('Mô tả mới cần giữ'.encode(), response.data)
        self.assertIn(b'name="price_per_day" class="form-control" value=""', response.data)
        self.assertIn(b'name="variant_quantity[]" class="form-control" min="0" value="1"', response.data)
        with app.app_context():
            product = db.session.get(Product, product_id)
            self.assertEqual(product.name, 'Áo dài đỏ')

    def test_admin_can_update_product_from_edit_form(self):
        product_id = self.create_product(quantity=3)
        with app.app_context():
            product = db.session.get(Product, product_id)
            product.image_url = '/static/uploads/product.jpg'
            db.session.commit()
        self.login_admin()
        edit_page = self.client.get(f'/edit-product/{product_id}')
        self.assertEqual(edit_page.status_code, 200)
        self.assertIn(b'type="text" name="image_url"', edit_page.data)
        self.assertIn(b'value="/static/uploads/product.jpg"', edit_page.data)
        sizes = ('XS', 'S', 'M', 'L', 'XL', 'XXL')
        response = self.client.post(f'/edit-product/{product_id}', data={
            '_csrf_token': self.csrf(f'/edit-product/{product_id}'),
            'name': 'Áo đã cập nhật', 'category': 'Phụ kiện',
            'description': 'Mô tả cập nhật', 'price_per_day': '150000', 'deposit': '50000',
            'image_url': '/static/uploads/product.jpg',
            'variant_gender[]': ['male'] * len(sizes),
            'variant_size[]': list(sizes), 'variant_quantity[]': ['0', '0', '3', '0', '0', '0'],
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            product = db.session.get(Product, product_id)
            self.assertEqual(product.name, 'Áo đã cập nhật')
            self.assertEqual(product.category, 'Phụ kiện')
            self.assertEqual(product.description, 'Mô tả cập nhật')
            self.assertEqual(product.price_per_day, 150000)
            self.assertEqual(product.deposit, 50000)
            self.assertEqual(product.quantity, 3)
            self.assertEqual(product.image_url, '/static/uploads/product.jpg')

    def test_public_pages_and_csrf_protection(self):
        for path in ('/health', '/rent', '/customer/register', '/login', '/admin/login'):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get('/customer/login').status_code, 404)
        self.assertIn(b'/customer/forgot-password', self.client.get('/login').data)
        self.assertIn(b'/admin/forgot-password', self.client.get('/admin/login').data)
        self.assertEqual(self.client.get('/checkout').status_code, 302)
        self.assertIn('/login?next=', self.client.get('/checkout').location)
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

    def test_customer_product_detail_has_seo_and_is_in_sitemap(self):
        product_id = self.create_product()
        detail = self.client.get(f'/san-pham/{product_id}')
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b'Product', detail.data)
        self.assertIn(f'/san-pham/{product_id}'.encode(), detail.data)
        self.assertIn(b'<meta name="robots" content="index, follow">', detail.data)
        sitemap = self.client.get('/sitemap.xml')
        self.assertIn(f'/san-pham/{product_id}</loc>'.encode(), sitemap.data)

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
                'payment_receipt': (io.BytesIO(b'\x89PNG\r\n\x1a\nvalid-test-image'), 'receipt.png')},
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
                     '/rentals/999/confirm-payment', '/logout', '/customer/logout'):
            self.assertEqual(self.client.get(path).status_code, 405, path)

    def test_admin_pages_render(self):
        self.create_product()
        self.login_admin()
        for path in ('/dashboard', '/customers', '/products', '/categories', '/add-product',
                     '/rentals', '/add-rental', '/reports'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_rentals_date_to_includes_the_entire_selected_day(self):
        with app.app_context():
            customer = Customer(fullname='Nguyen Test', phone='0900000091')
            db.session.add(customer)
            db.session.flush()
            db.session.add_all([
                Rental(rental_code='DATE-IN', customer_id=customer.id,
                       start_date=datetime(2026, 8, 9), end_date=datetime(2026, 8, 10, 18),
                       status='returned'),
                Rental(rental_code='DATE-OUT', customer_id=customer.id,
                       start_date=datetime(2026, 8, 10), end_date=datetime(2026, 8, 11),
                       status='returned'),
            ])
            db.session.commit()
        self.login_admin()
        response = self.client.get('/rentals?date_to=2026-08-10')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'DATE-IN', response.data)
        self.assertNotIn(b'DATE-OUT', response.data)

    def test_rentals_can_filter_payment_proofs_awaiting_confirmation(self):
        with app.app_context():
            customer = Customer(fullname='Nguyen Payment', phone='0900000092')
            db.session.add(customer)
            db.session.flush()
            db.session.add_all([
                Rental(rental_code='PAYMENT-REVIEW', customer_id=customer.id,
                       start_date=datetime(2026, 8, 9), end_date=datetime(2026, 8, 10),
                       status='pending', payment_status='customer_submitted'),
                Rental(rental_code='PAYMENT-OTHER', customer_id=customer.id,
                       start_date=datetime(2026, 8, 9), end_date=datetime(2026, 8, 10),
                       status='rented', payment_status='pending_confirmation'),
            ])
            db.session.commit()
        self.login_admin()
        dashboard = self.client.get('/dashboard')
        self.assertIn(b'payment_status=customer_submitted', dashboard.data)
        response = self.client.get('/rentals?payment_status=customer_submitted')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'PAYMENT-REVIEW', response.data)
        self.assertNotIn(b'PAYMENT-OTHER', response.data)

    def test_admin_customers_page_renders_with_existing_customers(self):
        with app.app_context():
            db.session.add(Customer(fullname='Nguyễn Thị B', phone='0900000011',
                                    email='b@example.com'))
            db.session.commit()
        self.login_admin()
        response = self.client.get('/customers')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Nguyễn Thị B'.encode(), response.data)

    def test_admin_can_edit_customer_details(self):
        with app.app_context():
            customer = Customer(fullname='Nguyễn Thị C', phone='0900000012',
                                email='c@example.com')
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id
        self.login_admin()
        response = self.client.get(f'/edit-customer/{customer_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Nguyễn Thị C'.encode(), response.data)

        response = self.client.post(f'/edit-customer/{customer_id}', data={
            '_csrf_token': self.csrf(f'/edit-customer/{customer_id}'),
            'fullname': 'Nguyễn Thị C2', 'phone': '0900000013',
            'email': 'c2@example.com', 'id_card': '123456789',
            'address': 'Đồng Tháp', 'notes': 'Khách ưu tiên'})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            customer = db.session.get(Customer, customer_id)
            self.assertEqual(customer.fullname, 'Nguyễn Thị C2')
            self.assertEqual(customer.phone, '0900000013')
            self.assertEqual(customer.notes, 'Khách ưu tiên')

    def test_edit_customer_rejects_duplicate_phone(self):
        with app.app_context():
            db.session.add(Customer(fullname='Khách Một', phone='0900000014'))
            db.session.add(Customer(fullname='Khách Hai', phone='0900000015'))
            db.session.commit()
            second_id = Customer.query.filter_by(phone='0900000015').one().id
        self.login_admin()
        response = self.client.post(f'/edit-customer/{second_id}', data={
            '_csrf_token': self.csrf(f'/edit-customer/{second_id}'),
            'fullname': 'Khách Hai', 'phone': '0900000014'})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(Customer, second_id).phone, '0900000015')

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
                'variant_gender[]': ['unisex'], 'variant_size[]': ['M'],
                'variant_quantity[]': ['1'],
                'image_url': 'https://example.com/old.jpg',
                'camera_image': (io.BytesIO(b'\xff\xd8\xffvalid-test-image'), 'camera.jpg')},
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

    def test_product_supports_male_and_female_variant_inventory(self):
        self.login_admin()
        response = self.client.post('/add-product', data={
            '_csrf_token': self.csrf('/add-product'), 'name': 'Trang phục đôi',
            'category': 'Biểu diễn', 'price_per_day': '200000', 'deposit': '0',
            'variant_gender[]': ['male', 'female'],
            'variant_size[]': ['M', 'S'],
            'variant_quantity[]': ['5', '4']})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            product = Product.query.filter_by(name='Trang phục đôi').one()
            self.assertEqual(product.quantity, 9)
            self.assertEqual(product.available_quantity, 9)
            self.assertEqual(len(product.variant_list), 2)
            self.assertEqual(product.variant_list[1]['gender'], 'female')
            product_id = product.id

        storefront = self.client.get('/rent')
        self.assertIn('Nam · Size M · Còn 5'.encode(), storefront.data)
        self.assertIn('Nữ · Size S · Còn 4'.encode(), storefront.data)
        self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Khách biến thể',
            'phone': '0900000888', 'email': 'variant@example.com', 'password': 'secret1'})
        response = self.client.post('/checkout', data={
            '_csrf_token': self.csrf('/checkout'), 'fullname': 'Khách biến thể',
            'phone': '0900000888', 'start_date': '2026-10-01', 'end_date': '2026-10-03',
            'product_id[]': [str(product_id)], 'gender[]': ['male'],
            'size[]': ['M'], 'quantity[]': ['1']})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            product = db.session.get(Product, product_id)
            self.assertEqual(product.variant_list[0]['available'], 4)
            detail = RentalDetail.query.filter_by(product_id=product_id).one()
            self.assertEqual(detail.selected_gender, 'male')

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

    def test_reports_dashboard_renders_selected_period_and_chart_data(self):
        self.login_admin()
        response = self.client.get('/reports?report_type=month&period=2026-10')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="reports-page"', response.data)
        self.assertIn(b'id="reportType"', response.data)
        self.assertIn(b'id="reportPeriod"', response.data)
        self.assertIn(b'id="revenueChart"', response.data)
        self.assertIn(b'T&#7893;ng doanh thu', response.data)


    def test_admin_can_open_rental_details_and_mark_cash_order_paid(self):
        product_id = self.create_product(quantity=2)
        self.login_admin()
        self.client.post('/add-rental', data={
            '_csrf_token': self.csrf('/add-rental'), 'customer_mode': 'guest',
            'guest_name': 'Khách xem đơn', 'guest_phone': '0900000044',
            'start_date': '2026-08-10', 'end_date': '2026-08-12',
            'product_id[]': [str(product_id)], 'quantity[]': ['1']})
        with app.app_context():
            rental = Rental.query.one()
            rental_id = rental.id
            self.assertEqual(rental.payment_status, 'unpaid')

        detail = self.client.get(f'/rentals/{rental_id}')
        self.assertEqual(detail.status_code, 200)
        self.assertIn('Áo dài đỏ'.encode(), detail.data)
        self.assertIn(b'Ch&#432;a thanh to&#225;n', detail.data)
        listing = self.client.get('/rentals')
        self.assertIn(f'href="/rentals/{rental_id}"'.encode(), listing.data)

        response = self.client.post(f'/rentals/{rental_id}/confirm-payment', data={
            '_csrf_token': self.csrf(f'/rentals/{rental_id}')})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = db.session.get(Rental, rental_id)
            self.assertEqual(rental.payment_status, 'paid')
            self.assertIsNotNone(rental.paid_at)
        self.assertIn(b'&#272;&#227; thanh to&#225;n', self.client.get(f'/rentals/{rental_id}').data)
        paid_orders = self.client.get('/rentals?payment_status=paid')
        self.assertIn(rental.rental_code.encode(), paid_orders.data)

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

    def test_admin_can_add_and_update_signed_order_adjustment(self):
        product_id = self.create_product(quantity=2)
        self.login_admin()
        response = self.client.post('/add-rental', data={
            '_csrf_token': self.csrf('/add-rental'), 'customer_mode': 'guest',
            'guest_name': 'Khách thuê ngoài', 'guest_phone': '0900000777',
            'start_date': '2026-11-01', 'end_date': '2026-11-03',
            'product_id[]': [str(product_id)], 'quantity[]': ['1'],
            'adjustment_amount': '200000',
            'adjustment_note': 'Thuê thêm trang phục bên ngoài'})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = Rental.query.one()
            rental_id = rental.id
            self.assertEqual(rental.total_amount, 400000)
            self.assertEqual(rental.adjustment_amount, 200000)

        response = self.client.post(f'/rentals/{rental_id}/adjustment', data={
            '_csrf_token': self.csrf('/rentals'), 'adjustment_amount': '-50000',
            'adjustment_note': 'Giảm giá hỗ trợ'})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            rental = db.session.get(Rental, rental_id)
            self.assertEqual(rental.total_amount, 150000)
            self.assertEqual(rental.adjustment_note, 'Giảm giá hỗ trợ')

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
