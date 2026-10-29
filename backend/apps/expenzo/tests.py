from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
import json

class ScanReceiptAPITestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()
        self.client.login(username='testuser', password='password123')

    def test_scan_receipt_ok(self):
        url = reverse('api_scan_receipt')
        payload = {
            'text': 'Walmart\nDate: 2026-05-15\nTotal: 150.25\nUPI payment',
            'ocr_confidence': 95.0
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

    def test_scan_receipt_none_text(self):
        url = reverse('api_scan_receipt')
        payload = {
            'text': None,
            'ocr_confidence': 85.0
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        print("NONE TEXT RESPONSE:", response.status_code, response.content)
        # We want this to return 400 or 200, not crash (500)
        self.assertIn(response.status_code, [400, 200])

    def test_scan_receipt_html(self):
        url = reverse('api_scan_receipt')
        payload = {
            'text': '<html><body><h1>Target</h1>Date: 12/12/2025<br>Total: $12.34</body></html>',
            'ocr_confidence': 90.0
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

    def test_scan_receipt_empty(self):
        url = reverse('api_scan_receipt')
        payload = {
            'text': '   ',
            'ocr_confidence': 0.0
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_scan_receipt_no_confidence(self):
        url = reverse('api_scan_receipt')
        payload = {
            'text': 'Only text here with no numbers.'
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)


class AuthPagesTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            username='alex@example.com',
            email='alex@example.com',
            password='ComplexPassword@2026'
        )

    def tearDown(self):
        cache.clear()

    def test_login_page_renders_design(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'login.html')
        content = response.content.decode('utf-8')
        self.assertIn('EXPENZO', content)
        self.assertIn('Welcome back.', content)
        self.assertIn('Encrypted Tunnel', content)
        self.assertIn('Real-time Financial Velocity', content)
        self.assertIn('name="email"', content)
        self.assertIn('name="password"', content)
        self.assertIn('csrfmiddlewaretoken', content)

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login'), {
            'email': 'alex@example.com',
            'password': 'WrongPassword123!'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'login.html')
        content = response.content.decode('utf-8')
        self.assertIn('Invalid credentials', content)

    def test_login_success(self):
        response = self.client.post(reverse('login'), {
            'email': 'alex@example.com',
            'password': 'ComplexPassword@2026'
        })
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_register_page_renders_design(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'register.html')
        content = response.content.decode('utf-8')
        self.assertIn('EXPENZO', content)
        self.assertIn('Start your financial journey.', content)
        self.assertIn('Free Forever Tier', content)
        self.assertIn('Real-time Financial Velocity', content)
        self.assertIn('name="name"', content)
        self.assertIn('name="email"', content)
        self.assertIn('name="password"', content)
        self.assertIn('name="confirm_password"', content)
        self.assertIn('csrfmiddlewaretoken', content)

    def test_register_password_mismatch(self):
        response = self.client.post(reverse('register'), {
            'name': 'New User',
            'email': 'newuser@example.com',
            'password': 'ComplexPassword@2026',
            'confirm_password': 'MismatchedPassword@2026',
            'terms': 'on'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'register.html')
        content = response.content.decode('utf-8')
        self.assertIn('Passwords do not match', content)

    def test_register_existing_user(self):
        response = self.client.post(reverse('register'), {
            'name': 'Existing User',
            'email': 'alex@example.com',
            'password': 'ComplexPassword@2026',
            'confirm_password': 'ComplexPassword@2026',
            'terms': 'on'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'register.html')
        content = response.content.decode('utf-8')
        self.assertIn('User with this email already exists', content)

    def test_register_success(self):
        response = self.client.post(reverse('register'), {
            'name': 'Jordan Smith',
            'email': 'jordan@example.com',
            'password': 'ComplexPassword@2026',
            'confirm_password': 'ComplexPassword@2026',
            'terms': 'on'
        })
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(email='jordan@example.com').exists())
        self.assertTrue('_auth_user_id' in self.client.session)
