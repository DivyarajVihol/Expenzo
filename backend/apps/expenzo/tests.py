from django.test import TestCase, Client
from django.contrib.auth.models import User
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
