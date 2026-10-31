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


class PerformanceAndOptimizationTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='perf_user',
            email='perf_user@example.com',
            password='StrongPassword123!'
        )
        self.client = Client()
        self.client.login(username='perf_user', password='StrongPassword123!')

    def tearDown(self):
        cache.clear()

    def test_recurring_finance_idempotency_no_duplicates(self):
        """Calling process_recurring_finance repeatedly must never duplicate transactions."""
        from .models import RecurringIncome, RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance
        from django.utils import timezone
        now = timezone.now()

        # Create active recurring income & expense
        income = RecurringIncome.objects.create(
            user=self.user,
            name="Salary",
            amount=50000.0,
            execution_day=1,
            is_active=True
        )
        expense = RecurringExpense.objects.create(
            user=self.user,
            name="Internet",
            amount=1000.0,
            execution_day=1,
            is_active=True
        )

        # First run: generates records
        process_recurring_finance(self.user)
        initial_count = PersonalExpense.objects.filter(user=self.user, is_recurring=True).count()
        self.assertGreater(initial_count, 0)

        # Clear process cache to simulate subsequent runs or separate requests
        cache.clear()

        # Second run: must NOT create duplicate transactions
        process_recurring_finance(self.user)
        second_count = PersonalExpense.objects.filter(user=self.user, is_recurring=True).count()
        self.assertEqual(initial_count, second_count)

    def test_recalculate_current_month_preserves_manual_and_past_expenses(self):
        """Recalculation must never delete manual expenses or past month recurring records."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance, recalculate_current_month
        from django.utils import timezone
        now = timezone.now()

        # Create manual expense in current month
        manual_exp = PersonalExpense.objects.create(
            user=self.user,
            amount=250.0,
            category="Food",
            payment_method="UPI",
            account="Bank Account",
            description="Lunch Manual",
            date=now,
            month=now.month,
            year=now.year,
            is_recurring=False
        )

        # Create recurring item and process
        rec = RecurringExpense.objects.create(
            user=self.user,
            name="Gym",
            amount=2000.0,
            execution_day=1,
            is_active=True
        )
        process_recurring_finance(self.user)

        # Recalculate
        recalculate_current_month(self.user)

        # Manual expense must still exist
        self.assertTrue(PersonalExpense.objects.filter(id=manual_exp.id).exists())

        # Current month recurring expense must exist exactly once
        current_gym = PersonalExpense.objects.filter(
            user=self.user,
            description="Fixed Expense: Gym",
            month=now.month,
            year=now.year
        )
        self.assertEqual(current_gym.count(), 1)

    def test_dashboard_aggregations_and_query_count(self):
        """Dashboard view must aggregate in database without loading all expense records into Python."""
        from .models import PersonalExpense
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from django.utils import timezone
        now = timezone.now()

        # Seed 15 expenses
        for i in range(15):
            PersonalExpense.objects.create(
                user=self.user,
                amount=100.0 + i,
                category="Food" if i % 2 == 0 else "Income",
                payment_method="UPI" if i % 2 == 0 else "Bank Transfer",
                account="Bank Account",
                description=f"Item {i}",
                date=now,
                month=now.month,
                year=now.year,
                is_recurring=False
            )

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse('dashboard'))
            self.assertEqual(response.status_code, 200)
            self.assertIn('monthly_balance', response.context)
            self.assertIn('total_income', response.context)
            self.assertIn('total_expense', response.context)
            self.assertIn('account_breakdown', response.context)
            self.assertIn('payment_method_breakdown', response.context)
            # Must execute very few queries regardless of expense count
            self.assertLessEqual(len(ctx), 15)

    def test_liquidity_history_accuracy_and_caching(self):
        """Liquidity history returns 12 months data and caches the result."""
        from .models import PersonalExpense
        from .views import get_user_liquidity_history
        from django.utils import timezone
        now = timezone.now()

        PersonalExpense.objects.create(
            user=self.user,
            amount=5000.0,
            category="Income",
            payment_method="Bank Transfer",
            account="Bank Account",
            description="Bonus",
            date=now,
            month=now.month,
            year=now.year,
            is_recurring=False
        )

        # First call: computes and caches
        history1 = get_user_liquidity_history(self.user)
        self.assertEqual(len(history1), 12)
        self.assertEqual(history1[-1]['month_num'], now.month)
        self.assertGreaterEqual(history1[-1]['closingBalance'], 5000.0)

        # Cache must be populated
        cached = cache.get(f"liquidity_hist_{self.user.id}")
        self.assertIsNotNone(cached)

        # API endpoint uses cache
        response = self.client.get(reverse('api_liquidity_history'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['history']), 12)

    def test_groups_view_eliminates_n_plus_one(self):
        """Groups view should query all member counts and expense sums without N+1 queries."""
        from .models import Group, GroupMember, GroupExpense
        from django.utils import timezone
        now = timezone.now()

        # Create 5 groups for this user
        for i in range(5):
            g = Group.objects.create(name=f"Group {i}", created_by=self.user)
            GroupMember.objects.create(group=g, user=self.user, role='ADMIN')
            GroupExpense.objects.create(
                group=g,
                paid_by=self.user,
                amount=500.0 * (i + 1),
                description=f"Group Dinner {i}",
                category="Food",
                date=now
            )

        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse('groups'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['groups']), 5)
            self.assertEqual(response.context['total_groups_count'], 5)
            self.assertLessEqual(len(ctx), 8)

    def test_group_detail_view_no_loop_queries(self):
        """Group detail view should prefetch active UPIs and not issue queries in the debt loop."""
        from .models import Group, GroupMember, GroupExpense, GroupExpenseSplit, MemberUpiId
        from django.utils import timezone
        now = timezone.now()

        other_user = User.objects.create_user(username='other_u', email='other@example.com', password='Password123!')
        MemberUpiId.objects.create(user=other_user, upi_id='other@okaxis', is_active=True)

        g = Group.objects.create(name="Trip Group", created_by=self.user)
        GroupMember.objects.create(group=g, user=self.user, role='ADMIN')
        GroupMember.objects.create(group=g, user=other_user, role='MEMBER')

        exp = GroupExpense.objects.create(
            group=g,
            paid_by=self.user,
            amount=200.0,
            description="Hotel",
            category="Travel",
            date=now
        )
        GroupExpenseSplit.objects.create(group_expense=exp, user=self.user, amount=100.0)
        GroupExpenseSplit.objects.create(group_expense=exp, user=other_user, amount=100.0)

        response = self.client.get(reverse('group_detail', args=[g.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['debts']), 1)
        debt = response.context['debts'][0]
        self.assertEqual(debt['fromUserId'], other_user.id)
        self.assertEqual(debt['toUserId'], self.user.id)
        self.assertEqual(debt['amount'], 100.0)

