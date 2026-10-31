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

    def test_two_recurring_items_with_identical_names_generate_separate_transactions(self):
        """Two recurring items with the exact same name must generate distinct transactions."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance
        from django.utils import timezone
        now = timezone.now()

        item1 = RecurringExpense.objects.create(
            user=self.user,
            name="Internet",
            amount=500.0,
            execution_day=1,
            is_active=True
        )
        item2 = RecurringExpense.objects.create(
            user=self.user,
            name="Internet",
            amount=1000.0,
            execution_day=1,
            is_active=True
        )

        process_recurring_finance(self.user)

        # Both items must have generated separate transactions
        exp1 = PersonalExpense.objects.filter(recurring_expense=item1, year=now.year, month=now.month)
        exp2 = PersonalExpense.objects.filter(recurring_expense=item2, year=now.year, month=now.month)
        self.assertEqual(exp1.count(), 1)
        self.assertEqual(exp2.count(), 1)
        self.assertEqual(exp1.first().amount, 500.0)
        self.assertEqual(exp2.first().amount, 1000.0)

    def test_inactive_recurring_items_preserved_during_recalculation(self):
        """Inactive recurring items must not have their already-executed transactions deleted on recalculate."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance, recalculate_current_month
        from django.utils import timezone
        now = timezone.now()

        active_item = RecurringExpense.objects.create(
            user=self.user,
            name="Active Subscription",
            amount=300.0,
            execution_day=1,
            is_active=True
        )
        inactive_item = RecurringExpense.objects.create(
            user=self.user,
            name="Canceled Gym",
            amount=1500.0,
            execution_day=1,
            is_active=True  # active when created and run
        )

        process_recurring_finance(self.user)

        # Deactivate the gym
        inactive_item.is_active = False
        inactive_item.save(update_fields=['is_active'])

        # Run global recalculation
        recalculate_current_month(self.user)

        # Inactive item transaction must still be preserved!
        self.assertTrue(PersonalExpense.objects.filter(recurring_expense=inactive_item, month=now.month, year=now.year).exists())
        # Active item must also exist
        self.assertTrue(PersonalExpense.objects.filter(recurring_expense=active_item, month=now.month, year=now.year).exists())

    def test_editing_recurring_item_targets_only_its_transactions(self):
        """Editing one recurring item must only update that item's transaction, leaving others untouched."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance, recalculate_current_month
        from django.utils import timezone
        now = timezone.now()

        item_a = RecurringExpense.objects.create(
            user=self.user,
            name="Netflix",
            amount=499.0,
            execution_day=1,
            is_active=True
        )
        item_b = RecurringExpense.objects.create(
            user=self.user,
            name="Spotify",
            amount=119.0,
            execution_day=1,
            is_active=True
        )

        process_recurring_finance(self.user)
        spotify_tx = PersonalExpense.objects.get(recurring_expense=item_b, month=now.month, year=now.year)
        spotify_tx_id = spotify_tx.id

        # Edit item A (Netflix price increase)
        item_a.amount = 649.0
        item_a.save()
        recalculate_current_month(self.user, target_item=item_a)

        # Netflix transaction must be updated to 649
        netflix_tx = PersonalExpense.objects.get(recurring_expense=item_a, month=now.month, year=now.year)
        self.assertEqual(netflix_tx.amount, 649.0)

        # Spotify transaction must remain completely untouched (same ID and amount)
        self.assertTrue(PersonalExpense.objects.filter(id=spotify_tx_id, amount=119.0).exists())

    def test_deleting_recurring_item_preserves_historical_records_with_set_null(self):
        """Deleting a recurring item must preserve historical transactions and set foreign key to NULL."""
        from .models import RecurringExpense, PersonalExpense
        from django.utils import timezone
        now = timezone.now()

        item = RecurringExpense.objects.create(
            user=self.user,
            name="Legacy Utility",
            amount=800.0,
            execution_day=1,
            is_active=True
        )

        # Create past month transaction
        past_tx = PersonalExpense.objects.create(
            user=self.user,
            amount=800.0,
            category="Others",
            payment_method="UPI",
            account="Bank Account",
            description="Fixed Expense: Legacy Utility",
            date=now - timezone.timedelta(days=60),
            month=1,
            year=now.year - 1 if now.month <= 2 else now.year,
            is_recurring=True,
            recurring_expense=item
        )

        # Delete the recurring item rule
        item_id = item.id
        item.delete()

        # The historical transaction must NOT be deleted; foreign key becomes NULL
        past_tx.refresh_from_db()
        self.assertIsNone(past_tx.recurring_expense)
        self.assertEqual(past_tx.amount, 800.0)
        self.assertTrue(past_tx.is_recurring)

    def test_database_unique_constraint_prevents_simultaneous_worker_duplicate(self):
        """Database UniqueConstraint prevents duplicate monthly transactions for same recurring item."""
        from .models import RecurringExpense, PersonalExpense
        from django.db import IntegrityError
        from django.utils import timezone
        now = timezone.now()

        item = RecurringExpense.objects.create(
            user=self.user,
            name="Hosting",
            amount=1200.0,
            execution_day=1,
            is_active=True
        )

        # First insert succeeds
        PersonalExpense.objects.create(
            user=self.user,
            amount=1200.0,
            category="Others",
            payment_method="UPI",
            account="Bank Account",
            description="Fixed Expense: Hosting",
            date=now,
            month=now.month,
            year=now.year,
            is_recurring=True,
            recurring_expense=item
        )

        # Second insert for same item, year, month MUST raise IntegrityError at database level
        with self.assertRaises(IntegrityError):
            PersonalExpense.objects.create(
                user=self.user,
                amount=1200.0,
                category="Others",
                payment_method="UPI",
                account="Bank Account",
                description="Fixed Expense: Hosting Duplicate",
                date=now,
                month=now.month,
                year=now.year,
                is_recurring=True,
                recurring_expense=item
            )

    def test_check_constraint_prevents_dual_recurring_source(self):
        """Database CheckConstraint prevents an expense from being linked to both income and expense."""
        from .models import RecurringIncome, RecurringExpense, PersonalExpense
        from django.db import IntegrityError
        from django.utils import timezone
        now = timezone.now()

        inc = RecurringIncome.objects.create(user=self.user, name="Inc", amount=1000.0)
        exp = RecurringExpense.objects.create(user=self.user, name="Exp", amount=500.0)

        with self.assertRaises(IntegrityError):
            PersonalExpense.objects.create(
                user=self.user,
                amount=500.0,
                category="Others",
                payment_method="UPI",
                account="Bank Account",
                description="Invalid dual source",
                date=now,
                month=now.month,
                year=now.year,
                is_recurring=True,
                recurring_income=inc,
                recurring_expense=exp
            )

    def test_concurrent_lock_exits_immediately(self):
        """When another process holds the cache lock, processing exits immediately without doing work."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance

        item = RecurringExpense.objects.create(
            user=self.user,
            name="Electricity",
            amount=1500.0,
            execution_day=1,
            is_active=True
        )

        # Simulate another process holding the lock
        lock_key = f"rec_lock_{self.user.id}"
        cache.set(lock_key, "1", timeout=30)

        # process_recurring_finance must exit immediately
        process_recurring_finance(self.user)

        # No expense should have been created because the lock was held
        self.assertFalse(PersonalExpense.objects.filter(recurring_expense=item).exists())

        # Cleanup lock and verify subsequent call acquires lock and succeeds
        cache.delete(lock_key)
        process_recurring_finance(self.user)
        self.assertTrue(PersonalExpense.objects.filter(recurring_expense=item).exists())

    def test_unauthorized_target_item_blocked(self):
        """A target item belonging to another user must be rejected and not processed."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance, recalculate_current_month

        other_user = User.objects.create_user(username='victim_user', password='Password123!')
        other_item = RecurringExpense.objects.create(
            user=other_user,
            name="Victim Bill",
            amount=2000.0,
            execution_day=1,
            is_active=True
        )

        # Attacker tries to process or recalculate other user's item
        process_recurring_finance(self.user, target_item=other_item)
        self.assertFalse(PersonalExpense.objects.filter(recurring_expense=other_item).exists())

        recalculate_current_month(self.user, target_item=other_item)
        self.assertFalse(PersonalExpense.objects.filter(recurring_expense=other_item).exists())

    def test_inactive_rules_not_processed(self):
        """Inactive recurring rules must never generate transactions."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance

        inactive_item = RecurringExpense.objects.create(
            user=self.user,
            name="Old Magazine",
            amount=250.0,
            execution_day=1,
            is_active=False
        )

        process_recurring_finance(self.user)
        self.assertFalse(PersonalExpense.objects.filter(recurring_expense=inactive_item).exists())

        # Explicit target_item call must also be ignored
        process_recurring_finance(self.user, target_item=inactive_item)
        self.assertFalse(PersonalExpense.objects.filter(recurring_expense=inactive_item).exists())

    def test_legacy_null_fk_reconciliation_no_duplicates(self):
        """Legacy transactions with NULL recurring foreign keys must be reconciled in-place without duplicate creation."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance
        from django.utils import timezone
        now = timezone.now()

        item = RecurringExpense.objects.create(
            user=self.user,
            name="Broadband",
            amount=799.0,
            execution_day=1,
            is_active=True
        )

        # Pre-existing legacy record created before foreign keys were introduced
        legacy_tx = PersonalExpense.objects.create(
            user=self.user,
            amount=799.0,
            category="Others",
            payment_method="UPI",
            account="Bank Account",
            description="Fixed Expense: Broadband",
            date=now,
            month=now.month,
            year=now.year,
            is_recurring=True,
            recurring_expense=None,
            recurring_income=None
        )

        # Run process_recurring_finance
        process_recurring_finance(self.user)

        # Must not create a duplicate transaction
        all_broadband = PersonalExpense.objects.filter(
            user=self.user,
            month=now.month,
            year=now.year,
            description="Fixed Expense: Broadband"
        )
        self.assertEqual(all_broadband.count(), 1)

        # Legacy transaction should have been linked to the item
        legacy_tx.refresh_from_db()
        self.assertEqual(legacy_tx.recurring_expense_id, item.id)

    def test_legacy_ambiguous_matches_preserved_without_arbitrary_link(self):
        """When multiple legacy records match, do not arbitrarily link one. Preserve all records without duplicating."""
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance
        from django.utils import timezone
        now = timezone.now()

        item = RecurringExpense.objects.create(
            user=self.user,
            name="Cloud Storage",
            amount=500.0,
            execution_day=1,
            is_active=True
        )

        # Create 2 ambiguous legacy records with identical descriptions and amounts
        legacy1 = PersonalExpense.objects.create(
            user=self.user,
            amount=500.0,
            category="Others",
            payment_method="UPI",
            account="Bank Account",
            description="Fixed Expense: Cloud Storage",
            date=now,
            month=now.month,
            year=now.year,
            is_recurring=True,
            recurring_expense=None
        )
        legacy2 = PersonalExpense.objects.create(
            user=self.user,
            amount=500.0,
            category="Others",
            payment_method="UPI",
            account="Bank Account",
            description="Fixed Expense: Cloud Storage",
            date=now,
            month=now.month,
            year=now.year,
            is_recurring=True,
            recurring_expense=None
        )

        process_recurring_finance(self.user)

        # No duplicate 3rd transaction created
        matching = PersonalExpense.objects.filter(
            user=self.user,
            month=now.month,
            year=now.year,
            description="Fixed Expense: Cloud Storage"
        )
        self.assertEqual(matching.count(), 2)

        # Neither ambiguous record was arbitrarily linked; both remain preserved
        legacy1.refresh_from_db()
        legacy2.refresh_from_db()
        self.assertIsNone(legacy1.recurring_expense)
        self.assertIsNone(legacy2.recurring_expense)

    def test_month_end_and_february_clamping(self):
        """Execution day 31 must clamp to month end (e.g. 28/29 for Feb, 30 for April)."""
        import calendar
        from datetime import datetime
        from .models import RecurringExpense, PersonalExpense
        from .recurring_processor import process_recurring_finance
        from django.utils import timezone
        from unittest.mock import patch

        item = RecurringExpense.objects.create(
            user=self.user,
            name="End of Month SIP",
            amount=5000.0,
            execution_day=31,
            is_active=True
        )

        # Mock current time to April 30, 2025 (April has 30 days)
        mock_april = timezone.make_aware(datetime(2025, 4, 30, 12, 0, 0))
        with patch('django.utils.timezone.now', return_value=mock_april):
            RecurringExpense.objects.filter(pk=item.pk).update(
                created_at=timezone.make_aware(datetime(2025, 4, 1, 0, 0, 0))
            )
            item.refresh_from_db()
            process_recurring_finance(self.user, target_item=item)

            tx_april = PersonalExpense.objects.filter(recurring_expense=item, year=2025, month=4).first()
            self.assertIsNotNone(tx_april)
            self.assertEqual(tx_april.date.day, 30)

        # Mock current time to Feb 28, 2025 (non-leap year, 28 days)
        item2 = RecurringExpense.objects.create(
            user=self.user,
            name="Feb Non-Leap SIP",
            amount=3000.0,
            execution_day=31,
            is_active=True
        )
        mock_feb_non_leap = timezone.make_aware(datetime(2025, 2, 28, 12, 0, 0))
        with patch('django.utils.timezone.now', return_value=mock_feb_non_leap):
            RecurringExpense.objects.filter(pk=item2.pk).update(
                created_at=timezone.make_aware(datetime(2025, 2, 1, 0, 0, 0))
            )
            item2.refresh_from_db()
            process_recurring_finance(self.user, target_item=item2)

            tx_feb = PersonalExpense.objects.filter(recurring_expense=item2, year=2025, month=2).first()
            self.assertIsNotNone(tx_feb)
            self.assertEqual(tx_feb.date.day, 28)

        # Mock current time to Feb 29, 2024 (leap year, 29 days)
        item3 = RecurringExpense.objects.create(
            user=self.user,
            name="Feb Leap SIP",
            amount=3000.0,
            execution_day=31,
            is_active=True
        )
        mock_feb_leap = timezone.make_aware(datetime(2024, 2, 29, 12, 0, 0))
        with patch('django.utils.timezone.now', return_value=mock_feb_leap):
            RecurringExpense.objects.filter(pk=item3.pk).update(
                created_at=timezone.make_aware(datetime(2024, 2, 1, 0, 0, 0))
            )
            item3.refresh_from_db()
            process_recurring_finance(self.user, target_item=item3)

            tx_feb_leap = PersonalExpense.objects.filter(recurring_expense=item3, year=2024, month=2).first()
            self.assertIsNotNone(tx_feb_leap)
            self.assertEqual(tx_feb_leap.date.day, 29)

    def test_failed_processing_retry_behavior(self):
        """If processing encounters an error, the completion cache flag must NOT be set, allowing retry."""
        from .models import RecurringExpense
        from .recurring_processor import process_recurring_finance
        from django.utils import timezone
        from unittest.mock import patch
        from django.db import OperationalError

        now = timezone.now()
        item = RecurringExpense.objects.create(
            user=self.user,
            name="Failing Item",
            amount=100.0,
            execution_day=1,
            is_active=True
        )

        done_cache_key = f"rec_done_{self.user.id}_{now.year}_{now.month}_{now.day}"
        cache.delete(done_cache_key)

        # Simulate database lock during create
        with patch('apps.expenzo.models.PersonalExpense.objects.create', side_effect=OperationalError("database is locked")):
            process_recurring_finance(self.user)

        # Done cache flag must NOT be set because had_error is True
        self.assertFalse(cache.get(done_cache_key))

        # Now without error, retry should succeed and set the cache flag
        process_recurring_finance(self.user)
        self.assertTrue(cache.get(done_cache_key))





class RecurringInactiveRecalculationRegressionTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from .models import RecurringExpense, PersonalExpense
        from django.utils import timezone
        self.user = User.objects.create_user(username="inactive_recalc_user", password="test-password")
        self.item = RecurringExpense.objects.create(
            user=self.user,
            name="Inactive Internet",
            amount=900.0,
            execution_day=1,
            is_active=False,
        )
        now = timezone.now()
        self.transaction = PersonalExpense.objects.create(
            user=self.user,
            amount=900.0,
            category="Others",
            payment_method="UPI",
            account="Bank Account",
            description="Fixed Expense: Inactive Internet",
            date=now,
            month=now.month,
            year=now.year,
            is_recurring=True,
            recurring_expense=self.item,
        )

    def test_targeted_recalculation_does_not_delete_inactive_rule_transaction(self):
        from .recurring_processor import recalculate_current_month
        recalculate_current_month(self.user, target_item=self.item)
        self.assertTrue(
            type(self.transaction).objects.filter(pk=self.transaction.pk).exists()
        )
