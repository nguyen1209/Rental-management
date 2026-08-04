import os
import tempfile
import unittest

TEST_DB = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
TEST_DB.close()
os.environ['DATABASE_URL'] = f"sqlite:///{TEST_DB.name.replace(os.sep, '/')}"
os.environ['SECRET_KEY'] = 'test-secret-key'

from app import app  # noqa: E402
from models import Admin, Product, Rental, db  # noqa: E402
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
        self.assertEqual(self.client.post('/customer/register', data={}).status_code, 400)
        self.assertEqual(self.client.get('/dashboard').status_code, 302)

    def test_customer_register_order_and_history(self):
        product_id = self.create_product()
        response = self.client.post('/customer/register', data={
            '_csrf_token': self.csrf('/customer/register'), 'fullname': 'Nguyễn An',
            'phone': '0900000001', 'email': 'an@example.com', 'password': 'secret1'})
        self.assertEqual(response.status_code, 302)
        response = self.client.post('/rent', data={
            '_csrf_token': self.csrf('/rent'), 'fullname': 'Nguyễn An',
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
                     '/cancel-rental/999', '/delete-rental/999'):
            self.assertEqual(self.client.get(path).status_code, 405, path)

    def test_admin_pages_render(self):
        self.create_product()
        self.login_admin()
        for path in ('/dashboard', '/customers', '/products', '/categories', '/add-product',
                     '/rentals', '/add-rental', '/reports'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

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


if __name__ == '__main__':
    unittest.main()
