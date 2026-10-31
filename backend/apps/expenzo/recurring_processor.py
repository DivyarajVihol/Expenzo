import calendar
import logging
from datetime import datetime

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone as django_timezone

from .models import PersonalExpense, RecurringIncome, RecurringExpense

logger = logging.getLogger(__name__)


def process_recurring_finance(user):
    """
    Process pending recurring income and expenses.

    - Protects against duplicate concurrent executions via atomic cache lock.
    - Employs fast cache bypass if already processed today.
    - Checks pending items with index-backed Q filter before opening transactions.
    - Prevents duplicate PersonalExpense records even under race conditions.
    - Preserves historical backdated processing, execution days, leap years and month-end clamping.
    - Updates last_processed markers cleanly.
    """
    if not user or not user.is_authenticated:
        return

    now = django_timezone.now()
    curr_year = now.year
    curr_month = now.month
    curr_day = now.day

    cache_done_key = f"rec_done_{user.id}_{curr_year}_{curr_month}_{curr_day}"
    if cache.get(cache_done_key):
        return

    lock_key = f"rec_lock_{user.id}"
    # Atomic lock with 15s expiration to prevent concurrent race conditions
    if not cache.add(lock_key, "1", timeout=15):
        return

    try:
        processing_models = [
            (RecurringIncome, True),
            (RecurringExpense, False),
        ]

        created_any = False

        for ItemModel, is_income in processing_models:
            # Quick check if any item is pending processing
            pending_items = ItemModel.objects.filter(
                user=user,
                is_active=True
            ).filter(
                Q(last_processed_year__isnull=True)
                | Q(last_processed_month__isnull=True)
                | Q(last_processed_year__lt=curr_year)
                | Q(last_processed_year=curr_year, last_processed_month__lt=curr_month)
            )

            if not pending_items.exists():
                continue

            try:
                with transaction.atomic():
                    # Process each pending active item
                    for item in pending_items.iterator():
                        if (
                            item.last_processed_year is None
                            or item.last_processed_month is None
                        ):
                            start_year = item.created_at.year
                            start_month = item.created_at.month
                        else:
                            start_year = item.last_processed_year
                            start_month = item.last_processed_month + 1
                            if start_month > 12:
                                start_month = 1
                                start_year += 1

                        y = start_year
                        m = start_month
                        last_processed = None

                        while (
                            y < curr_year
                            or (y == curr_year and m <= curr_month)
                        ):
                            last_day = calendar.monthrange(y, m)[1]
                            exec_day = min(item.execution_day, last_day)

                            # Do not process before the execution day for current month
                            if (
                                y == curr_year
                                and m == curr_month
                                and curr_day < exec_day
                            ):
                                break

                            process_date = django_timezone.make_aware(
                                datetime(y, m, exec_day, 0, 0, 0)
                            )
                            description = (
                                f"Fixed {'Income' if is_income else 'Expense'}: "
                                f"{item.name}"
                            )

                            # Idempotency guard: Prevent duplicate recurring transactions
                            already_exists = PersonalExpense.objects.filter(
                                user=user,
                                month=m,
                                year=y,
                                is_recurring=True,
                                description=description
                            ).exists()

                            if not already_exists:
                                PersonalExpense.objects.create(
                                    user=user,
                                    amount=item.amount,
                                    category="Income" if is_income else "Others",
                                    payment_method=item.payment_method,
                                    account=item.account,
                                    description=description,
                                    date=process_date,
                                    month=m,
                                    year=y,
                                    is_recurring=True
                                )
                                created_any = True

                            last_processed = (y, m)

                            m += 1
                            if m > 12:
                                m = 1
                                y += 1

                        if last_processed:
                            item.last_processed_year = last_processed[0]
                            item.last_processed_month = last_processed[1]
                            item.save(
                                update_fields=[
                                    "last_processed_year",
                                    "last_processed_month"
                                ]
                            )

            except Exception:
                logger.exception(
                    "Recurring finance processing failed for user %s (%s)",
                    user.pk,
                    ItemModel.__name__
                )

        if created_any:
            cache.delete(f"liquidity_hist_{user.id}")

        # Mark user as processed for today (expires in 30 minutes to allow re-checking)
        cache.set(cache_done_key, True, timeout=1800)

    finally:
        cache.delete(lock_key)


def recalculate_current_month(user):
    """
    Recalculate current month's recurring transactions.
    - Clears cached processing status.
    - Deletes ONLY is_recurring=True transactions for the current month and year.
    - Never touches manually created expenses (is_recurring=False) or other months.
    - Resets last_processed markers back to previous month.
    - Re-processes recurring items cleanly.
    """
    if not user or not user.is_authenticated:
        return

    now = django_timezone.now()
    curr_year = now.year
    curr_month = now.month

    # Clear cached flags
    cache.delete(f"rec_done_{user.id}_{curr_year}_{curr_month}_{now.day}")
    cache.delete(f"liquidity_hist_{user.id}")

    try:
        with transaction.atomic():
            # Safely remove only current month's generated recurring transactions.
            PersonalExpense.objects.filter(
                user=user,
                month=curr_month,
                year=curr_year,
                is_recurring=True
            ).delete()

            # Reset processing markers to previous month
            prev_year = curr_year - 1 if curr_month == 1 else curr_year
            prev_month = 12 if curr_month == 1 else curr_month - 1

            for ItemModel in (RecurringIncome, RecurringExpense):
                ItemModel.objects.filter(
                    user=user,
                    last_processed_year=curr_year,
                    last_processed_month=curr_month
                ).update(
                    last_processed_year=prev_year,
                    last_processed_month=prev_month
                )

        # Re-process after deletion commits
        process_recurring_finance(user)

    except Exception:
        logger.exception(
            "Recurring finance recalculation failed for user %s",
            user.pk
        )
