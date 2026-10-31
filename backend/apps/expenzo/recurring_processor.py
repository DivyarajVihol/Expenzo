import calendar
import uuid
import logging
from datetime import datetime

from django.core.cache import cache
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.utils import timezone as django_timezone

from .models import PersonalExpense, RecurringIncome, RecurringExpense

logger = logging.getLogger(__name__)


def process_recurring_finance(user, target_item=None):
    """
    Process pending recurring income and expenses.

    - Links PersonalExpense directly to its originating RecurringIncome or RecurringExpense.
    - Prevents duplicates using database UniqueConstraints and per-item checks.
    - Multiple items with identical names generate separate, distinct transactions.
    - Reconciles legacy records created before foreign keys were introduced to prevent past duplicates.
    - Concurrent requests are stopped early via cache lock; DB constraints provide final safety.
    - Completion cache flag is only set if processing completes without error.
    - Preserves historical backdated processing, execution days, leap years and month-end clamping.
    """
    if not user or not user.is_authenticated:
        return

    # Validate target_item ownership and active status if explicitly provided
    if target_item is not None:
        if getattr(target_item, 'user_id', None) != user.id:
            logger.warning(
                "SECURITY: Unauthorized recurring target_item access attempt. "
                "Item user: %s, Request user: %s",
                getattr(target_item, 'user_id', None),
                user.id
            )
            return

        if not target_item.is_active:
            return

        if not isinstance(target_item, (RecurringIncome, RecurringExpense)):
            logger.error("Invalid target_item type: %s", type(target_item))
            return

    now = django_timezone.now()
    curr_year = now.year
    curr_month = now.month
    curr_day = now.day

    cache_done_key = f"rec_done_{user.id}_{curr_year}_{curr_month}_{curr_day}"
    if target_item is None and cache.get(cache_done_key):
        return

    lock_key = f"rec_lock_{user.id}"
    lock_token = uuid.uuid4().hex
    # Stop processing immediately if this worker cannot acquire the advisory lock.
    if not cache.add(lock_key, lock_token, timeout=30):
        return

    created_any = False
    had_error = False

    try:
        if target_item is not None:
            if isinstance(target_item, RecurringIncome):
                processing_models = [(RecurringIncome, True, [target_item])]
            else:
                processing_models = [(RecurringExpense, False, [target_item])]
        else:
            processing_models = [
                (RecurringIncome, True, None),
                (RecurringExpense, False, None),
            ]

        for ItemModel, is_income, explicit_items in processing_models:
            if had_error:
                break
            if explicit_items is not None:
                items_to_process = explicit_items
            else:
                items_to_process = ItemModel.objects.filter(
                    user=user,
                    is_active=True
                ).filter(
                    Q(last_processed_year__isnull=True)
                    | Q(last_processed_month__isnull=True)
                    | Q(last_processed_year__lt=curr_year)
                    | Q(last_processed_year=curr_year, last_processed_month__lt=curr_month)
                )

                if not items_to_process.exists():
                    continue

            try:
                for item in items_to_process:
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
                        raw_day = getattr(item, 'execution_day', 1) or 1
                        last_day = calendar.monthrange(y, m)[1]
                        exec_day = min(max(1, raw_day), last_day)

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
                        expected_description = (
                            f"Fixed {'Income' if is_income else 'Expense'}: "
                            f"{item.name}"
                        )
                        expected_category = "Income" if is_income else "Others"

                        # 1. Primary check: duplicate check by source foreign key and month/year
                        if is_income:
                            already_exists = PersonalExpense.objects.filter(
                                recurring_income=item,
                                year=y,
                                month=m
                            ).exists()
                        else:
                            already_exists = PersonalExpense.objects.filter(
                                recurring_expense=item,
                                year=y,
                                month=m
                            ).exists()

                        # 2. Backward compatibility: check if legacy transaction exists with NULL FK
                        if not already_exists:
                            legacy_qs = PersonalExpense.objects.filter(
                                user=user,
                                year=y,
                                month=m,
                                is_recurring=True,
                                recurring_income__isnull=True,
                                recurring_expense__isnull=True,
                                description=expected_description,
                                category=expected_category
                            )
                            if legacy_qs.exists():
                                # A legacy recurring transaction already exists; prevent creating duplicates
                                already_exists = True

                                # Only link foreign key when match is strictly unambiguous
                                exact_amount_matches = legacy_qs.filter(amount=item.amount)
                                unambiguous_record = None

                                if exact_amount_matches.count() == 1:
                                    unambiguous_record = exact_amount_matches.first()
                                elif exact_amount_matches.count() == 0 and legacy_qs.count() == 1:
                                    unambiguous_record = legacy_qs.first()
                                else:
                                    ambiguous_count = legacy_qs.count()
                                    logger.warning(
                                        "Ambiguous legacy recurring records found for user %s, item %s (%s/%s). "
                                        "Found %d matching records. Preserving all records and retrying later.",
                                        user.pk, item.pk, m, y, ambiguous_count
                                    )
                                    # Do not advance this rule's processing marker: an ambiguous
                                    # legacy match may belong to another rule with identical details.
                                    had_error = True
                                    break

                                if unambiguous_record is not None:
                                    if is_income:
                                        unambiguous_record.recurring_income = item
                                        update_f = ["recurring_income"]
                                    else:
                                        unambiguous_record.recurring_expense = item
                                        update_f = ["recurring_expense"]
                                    try:
                                        unambiguous_record.save(update_fields=update_f)
                                    except IntegrityError:
                                        pass
                                    except OperationalError as oe:
                                        had_error = True
                                        logger.warning("Database lock updating legacy recurring record: %s", oe)
                                        break

                        if not already_exists:
                            try:
                                with transaction.atomic():
                                    PersonalExpense.objects.create(
                                        user=user,
                                        amount=item.amount,
                                        category=expected_category,
                                        payment_method=item.payment_method,
                                        account=item.account,
                                        description=expected_description,
                                        date=process_date,
                                        month=m,
                                        year=y,
                                        is_recurring=True,
                                        recurring_income=item if is_income else None,
                                        recurring_expense=item if not is_income else None,
                                    )
                                    created_any = True
                            except IntegrityError:
                                # Caught concurrent insert from another worker or constraint enforcement
                                logger.info(
                                    "Recurring transaction already created by concurrent process for item %s (%s/%s)",
                                    item.pk, m, y
                                )
                            except OperationalError as oe:
                                had_error = True
                                logger.warning(
                                    "Database lock encountered during recurring processing: %s", oe
                                )
                                break

                        last_processed = (y, m)

                        m += 1
                        if m > 12:
                            m = 1
                            y += 1

                    if last_processed:
                        try:
                            item.last_processed_year = last_processed[0]
                            item.last_processed_month = last_processed[1]
                            item.save(
                                update_fields=[
                                    "last_processed_year",
                                    "last_processed_month"
                                ]
                            )
                        except OperationalError as oe:
                            had_error = True
                            logger.warning(
                                "Database lock saving recurring marker for item %s: %s", item.pk, oe
                            )

            except Exception:
                had_error = True
                logger.exception(
                    "Recurring finance processing failed for user %s (%s)",
                    user.pk,
                    ItemModel.__name__
                )

        if created_any:
            cache.delete(f"liquidity_hist_{user.id}")

        # Set completion cache flag ONLY if all models succeeded without error and not targeting a single item
        if not had_error and target_item is None:
            cache.set(cache_done_key, True, timeout=1800)

    finally:
        # Do not remove a lock that may have expired and been reacquired by
        # another request while this processing run was still active.
        if cache.get(lock_key) == lock_token:
            cache.delete(lock_key)


def recalculate_current_month(user, target_item=None):
    """
    Recalculate current month's recurring transactions.
    
    - If target_item is provided:
        Recalculates ONLY for that specific item.
        Validates ownership and active status.
        Deletes ONLY that item's current-month transaction.
        Preserves all other recurring items, inactive items, and manual expenses.
    - If target_item is None (global recalculate):
        Recalculates ONLY for active recurring items (is_active=True).
        Never touches transactions of inactive recurring items.
        Never touches manual expenses (is_recurring=False).
        Never touches historical prior-month records.
    """
    if not user or not user.is_authenticated:
        return

    if target_item is not None:
        if getattr(target_item, 'user_id', None) != user.id:
            logger.warning(
                "SECURITY: Unauthorized recurring recalculate attempt on item %s by user %s",
                getattr(target_item, 'pk', None),
                user.id
            )
            return

        if not isinstance(target_item, (RecurringIncome, RecurringExpense)):
            logger.error("Invalid target_item type for recalculate: %s", type(target_item))
            return

        # Never delete a generated transaction when the rule is inactive.
        if not target_item.is_active:
            return

    now = django_timezone.now()
    curr_year = now.year
    curr_month = now.month

    prev_year = curr_year - 1 if curr_month == 1 else curr_year
    prev_month = 12 if curr_month == 1 else curr_month - 1

    # Invalidate cache flags
    cache.delete(f"rec_done_{user.id}_{curr_year}_{curr_month}_{now.day}")
    cache.delete(f"liquidity_hist_{user.id}")

    try:
        if target_item is not None:
            with transaction.atomic():
                if isinstance(target_item, RecurringIncome):
                    PersonalExpense.objects.filter(
                        user=user,
                        month=curr_month,
                        year=curr_year,
                        recurring_income=target_item
                    ).delete()
                elif isinstance(target_item, RecurringExpense):
                    PersonalExpense.objects.filter(
                        user=user,
                        month=curr_month,
                        year=curr_year,
                        recurring_expense=target_item
                    ).delete()

                # Reset marker if processed for current month
                if (
                    target_item.last_processed_year == curr_year
                    and target_item.last_processed_month == curr_month
                ):
                    target_item.last_processed_year = prev_year
                    target_item.last_processed_month = prev_month
                    target_item.save(update_fields=["last_processed_year", "last_processed_month"])

            if target_item.is_active:
                process_recurring_finance(user, target_item=target_item)

        else:
            # Global recalculate: only target ACTIVE recurring items
            active_incomes = RecurringIncome.objects.filter(user=user, is_active=True)
            active_expenses = RecurringExpense.objects.filter(user=user, is_active=True)

            with transaction.atomic():
                # Delete current month generated expenses ONLY for active items
                PersonalExpense.objects.filter(
                    user=user,
                    month=curr_month,
                    year=curr_year,
                    recurring_income__in=active_incomes
                ).delete()

                PersonalExpense.objects.filter(
                    user=user,
                    month=curr_month,
                    year=curr_year,
                    recurring_expense__in=active_expenses
                ).delete()

                # Reset markers for active items
                active_incomes.filter(
                    last_processed_year=curr_year,
                    last_processed_month=curr_month
                ).update(
                    last_processed_year=prev_year,
                    last_processed_month=prev_month
                )

                active_expenses.filter(
                    last_processed_year=curr_year,
                    last_processed_month=curr_month
                ).update(
                    last_processed_year=prev_year,
                    last_processed_month=prev_month
                )

            # Re-process active items
            process_recurring_finance(user)

    except Exception:
        logger.exception(
            "Recurring finance recalculation failed for user %s",
            user.pk
        )
