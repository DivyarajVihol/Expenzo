from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone as django_timezone
from django.db.models import Q
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger('security')

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils.html import strip_tags
from django.core.mail import send_mail
from django.urls import reverse
from django.core.cache import cache 
from django.core.files.storage import FileSystemStorage

from .models import (
    UserProfile, PersonalExpense, RecurringIncome, RecurringExpense,
    MonthlyRecurringProcessing, Group, GroupMember, GroupExpense,
    GroupExpenseSplit, Settlement, GroupExpensePayment, MemberUpiId
)
from .recurring_processor import process_recurring_finance, recalculate_current_month
from .charts import (
    generate_spending_pie_chart,
    generate_group_net_standing_chart, generate_payment_method_bar_chart
)
from .decorators import rate_limit

# Helper function to get get_object_or_404 substitute for clean usage
def get_object_or_none(model, **kwargs):
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        return None

@rate_limit(limit=60, window=60)
@login_required
def dashboard_view(request):
    user = request.user
    
    # Process recurring items dynamically
    process_recurring_finance(user)
    
    now = django_timezone.now()
    selected_year = now.year
    selected_month_num = now.month
    
    # Get filters
    filter_type = strip_tags(request.GET.get('filter', 'all'))
    search_query = strip_tags(request.GET.get('search', '').strip())[:100]
    
    # Fetch all personal expenses
    expenses = PersonalExpense.objects.filter(user=user).order_by('-date')
    
    # Apply search filter
    if search_query:
        expenses = expenses.filter(Q(description__icontains=search_query) | Q(category__icontains=search_query))
        
    # Apply date filter for recent transactions
    filtered_expenses = expenses
    
    if filter_type == 'daily':
        filtered_expenses = expenses.filter(date__date=now.date())
    elif filter_type == 'weekly':
        seven_days_ago = now.date() - timedelta(days=7)
        filtered_expenses = expenses.filter(date__date__gte=seven_days_ago, date__date__lte=now.date())
    elif filter_type == 'monthly':
        filtered_expenses = expenses.filter(date__year=now.year, date__month=now.month)
        
    recent_transactions = filtered_expenses[:20]
    
    # Compute active month stats
    monthly_expenses = PersonalExpense.objects.filter(user=user, date__year=selected_year, date__month=selected_month_num)
    
    # Cumulative balance calculation (carrying over balances from previous months)
    # Get last day of selected month
    if selected_month_num == 12:
        end_of_selected_month = django_timezone.make_aware(datetime(selected_year + 1, 1, 1, 23, 59, 59)) - timedelta(seconds=1)
    else:
        end_of_selected_month = django_timezone.make_aware(datetime(selected_year, selected_month_num + 1, 1, 23, 59, 59)) - timedelta(seconds=1)
        
    all_past_and_current_expenses = PersonalExpense.objects.filter(user=user, date__lte=end_of_selected_month)
    
    cumulative_income = sum(exp.amount for exp in all_past_and_current_expenses if exp.category == "Income")
    cumulative_spend = sum(exp.amount for exp in all_past_and_current_expenses if exp.category != "Income")
    monthly_balance = cumulative_income - cumulative_spend
    
    # Account & Payment Method Stats
    SUPPORTED_ACCOUNTS = ['Cash', 'Bank Account', 'Credit Card']
    SUPPORTED_METHODS = ['Cash', 'UPI', 'Debit Card', 'Credit Card', 'Bank Transfer']
    
    account_stats = {acc: {'income': 0.0, 'expense': 0.0, 'balance': 0.0} for acc in SUPPORTED_ACCOUNTS}
    account_stats['Others'] = {'income': 0.0, 'expense': 0.0, 'balance': 0.0}
    
    pm_stats = {method: {'income': 0.0, 'expense': 0.0, 'count': 0} for method in SUPPORTED_METHODS}
    pm_stats['Others'] = {'income': 0.0, 'expense': 0.0, 'count': 0}
    
    for exp in all_past_and_current_expenses:
        # Account logic
        acc = exp.account
        if acc not in SUPPORTED_ACCOUNTS:
            acc = 'Others'
            
        if exp.category == 'Income':
            account_stats[acc]['income'] += exp.amount
            account_stats[acc]['balance'] += exp.amount
        else:
            account_stats[acc]['expense'] += exp.amount
            account_stats[acc]['balance'] -= exp.amount
            
    for exp in monthly_expenses:
        # PM logic
        pm = exp.payment_method
        if pm == 'Net Banking' or pm == 'Bank Account':
            pm = 'Bank Transfer'
        if pm not in SUPPORTED_METHODS:
            pm = 'Others'
            
        if exp.category == 'Income':
            pm_stats[pm]['income'] += exp.amount
        else:
            pm_stats[pm]['expense'] += exp.amount
            pm_stats[pm]['count'] += 1
            
    if account_stats['Others']['income'] == 0 and account_stats['Others']['expense'] == 0:
        del account_stats['Others']
    if pm_stats['Others']['income'] == 0 and pm_stats['Others']['expense'] == 0:
        del pm_stats['Others']
        
    account_breakdown = []
    for name, data in account_stats.items():
        account_breakdown.append({
            'name': name,
            'income': data['income'],
            'expense': data['expense'],
            'balance': data['balance']
        })
        
    payment_method_breakdown = []
    for name, data in pm_stats.items():
        payment_method_breakdown.append({
            'name': name,
            'income': data['income'],
            'expense': data['expense'],
            'count': data['count']
        })
        
    pm_chart_base64 = generate_payment_method_bar_chart(pm_stats)
    
    # Calculate Pie Chart category breakdown
    category_sums = {}
    current_month_spends = monthly_expenses.exclude(category="Income")
    total_spend = sum(exp.amount for exp in current_month_spends)
    
    for exp in current_month_spends:
        category_sums[exp.category] = category_sums.get(exp.category, 0) + exp.amount
        
    category_breakdown = []
    pie_categories = []
    pie_values = []
    
    # Premium color matching
    COLORS = ["#818cf8", "#34d399", "#fb7185", "#fbbf24", "#a78bfa", "#22d3ee", "#f472b6", "#a7f3d0", "#c084fc", "#94a3b8"]
    
    for idx, (name, value) in enumerate(category_sums.items()):
        percentage = round((value / total_spend) * 100) if total_spend > 0 else 0
        category_breakdown.append({
            'name': name,
            'value': value,
            'percentage': percentage,
            'color': COLORS[idx % len(COLORS)]
        })
        pie_categories.append(name)
        pie_values.append(value)
        
    # Generate charts
    pie_chart_base64 = generate_spending_pie_chart(pie_categories, pie_values)
    
    active_month_label = now.strftime("%B %Y")
    
    import json
    account_balances_dict = {acc['name']: acc['balance'] for acc in account_breakdown}
    account_balances_json = json.dumps(account_balances_dict)
    
    context = {
        'recent_transactions': recent_transactions,
        'monthly_balance': monthly_balance,
        'active_month_label': active_month_label,
        'category_breakdown': category_breakdown,
        'pie_chart': pie_chart_base64,
        'account_breakdown': account_breakdown,
        'payment_method_breakdown': payment_method_breakdown,
        'pm_chart': pm_chart_base64,
        'filter_type': filter_type,
        'search_query': search_query,
        'account_balances_json': account_balances_json
    }
    return render(request, 'dashboard.html', context)


@rate_limit(limit=60, window=60)
@login_required
def charts_view(request):
    user = request.user
    
    # Process recurring items dynamically
    process_recurring_finance(user)
    
    now = django_timezone.now()
    selected_month = strip_tags(request.GET.get('month', '')).strip()
    
    if selected_month:
        try:
            selected_year, selected_month_num = map(int, selected_month.split('-'))
        except ValueError:
            selected_year = now.year
            selected_month_num = now.month
            selected_month = f"{selected_year}-{selected_month_num:02d}"
    else:
        selected_year = now.year
        selected_month_num = now.month
        selected_month = f"{selected_year}-{selected_month_num:02d}"
        
    # Get all distinct months with expenses for the dropdown selection
    expense_dates = PersonalExpense.objects.filter(user=user).dates('date', 'month', order='DESC')
    available_months = []
    for d in expense_dates:
        available_months.append({
            'key': d.strftime("%Y-%m"),
            'label': d.strftime("%B %Y")
        })
    
    # Ensure current selected month is in the list
    selected_label = datetime(selected_year, selected_month_num, 1).strftime("%B %Y")
    if not any(m['key'] == selected_month for m in available_months):
        available_months.insert(0, {
            'key': selected_month,
            'label': selected_label
        })
    
    # Compute active month stats
    monthly_expenses = PersonalExpense.objects.filter(user=user, date__year=selected_year, date__month=selected_month_num)
    
    # Calculate Pie Chart category breakdown
    category_sums = {}
    current_month_spends = monthly_expenses.exclude(category="Income")
    total_spend = sum(exp.amount for exp in current_month_spends)
    
    for exp in current_month_spends:
        category_sums[exp.category] = category_sums.get(exp.category, 0) + exp.amount
        
    category_breakdown = []
    pie_categories = []
    pie_values = []
    
    # Premium color matching
    COLORS = ["#818cf8", "#34d399", "#fb7185", "#fbbf24", "#a78bfa", "#22d3ee", "#f472b6", "#a7f3d0", "#c084fc", "#94a3b8"]
    
    for idx, (name, value) in enumerate(category_sums.items()):
        percentage = round((value / total_spend) * 100) if total_spend > 0 else 0
        category_breakdown.append({
            'name': name,
            'value': value,
            'percentage': percentage,
            'color': COLORS[idx % len(COLORS)]
        })
        pie_categories.append(name)
        pie_values.append(value)
        
    # Generate charts
    pie_chart_base64 = generate_spending_pie_chart(pie_categories, pie_values)
    
    import json
    all_expenses_data = []
    for exp in PersonalExpense.objects.filter(user=user).order_by('date'):
        all_expenses_data.append({
            'date': exp.date.strftime('%Y-%m-%d') if exp.date else '',
            'amount': float(exp.amount),
            'category': exp.category
        })
    all_expenses_json = json.dumps(all_expenses_data)
    
    context = {
        'category_breakdown': category_breakdown,
        'pie_chart': pie_chart_base64,
        'available_months': available_months,
        'selected_month': selected_month,
        'all_expenses_json': all_expenses_json
    }
    return render(request, 'charts.html', context)


@rate_limit(limit=60, window=60)
@login_required
def history_view(request):
    user = request.user
    
    # Get filters
    search_query = strip_tags(request.GET.get('search', '').strip())[:100]
    category_filter = strip_tags(request.GET.get('category', 'All').strip())[:50]
    account_filter = strip_tags(request.GET.get('account', 'All').strip())[:50]
    payment_filter = strip_tags(request.GET.get('paymentMethod', 'All').strip())[:50]
    
    expenses = PersonalExpense.objects.filter(user=user).order_by('-date')
    
    if search_query:
        expenses = expenses.filter(Q(description__icontains=search_query) | Q(category__icontains=search_query))
    if category_filter != 'All':
        expenses = expenses.filter(category=category_filter)
    if account_filter != 'All':
        expenses = expenses.filter(account=account_filter)
    if payment_filter != 'All':
        expenses = expenses.filter(payment_method=payment_filter)
        
    # Distinct categories, accounts, and payment methods for dropdown filters
    categories = ["Income", "Food", "Travel", "Shopping", "Entertainment", "Rent", "Utilities", "Health", "Education", "Investment", "Others"]
    accounts = ["Cash", "Bank Account", "Credit Card"]
    payment_methods = ["Cash", "UPI", "Debit Card", "Credit Card", "Bank Transfer"]
    
    # Group expenses by year and month
    from collections import defaultdict
    grouped_data = defaultdict(list)
    for exp in expenses:
        key = exp.date.strftime("%Y-%m")
        grouped_data[key].append(exp)

    grouped_months = []
    # Color mapping for UI
    CATEGORY_COLORS = {
        "Food": "#34d399",
        "Travel": "#fb7185",
        "Shopping": "#fbbf24",
        "Entertainment": "#a78bfa",
        "Rent": "#22d3ee",
        "Utilities": "#f472b6",
        "Health": "#a7f3d0",
        "Education": "#c084fc",
        "Investment": "#818cf8",
        "Others": "#94a3b8"
    }

    for key in sorted(grouped_data.keys(), reverse=True):
        exps = grouped_data[key]
        year, month = map(int, key.split('-'))
        label = datetime(year, month, 1).strftime("%B %Y")
        
        total_spend = sum(e.amount for e in exps if e.category != "Income")
        total_income = sum(e.amount for e in exps if e.category == "Income")
        
        # Calculate category breakdown
        category_sums = {}
        for e in exps:
            if e.category != "Income":
                category_sums[e.category] = category_sums.get(e.category, 0) + e.amount
                
        breakdown = []
        for cat_name, cat_val in category_sums.items():
            breakdown.append({
                'name': cat_name,
                'amount': cat_val,
                'color': CATEGORY_COLORS.get(cat_name, '#94a3b8')
            })
            
        grouped_months.append({
            'key': key,
            'label': label,
            'expenses': exps,
            'total_spend': total_spend,
            'total_income': total_income,
            'category_breakdown': breakdown
        })
        
    context = {
        'grouped_months': grouped_months,
        'categories': categories,
        'accounts': accounts,
        'payment_methods': payment_methods,
        'search_query': search_query,
        'selected_category': category_filter,
        'selected_account': account_filter,
        'selected_payment': payment_filter
    }
    return render(request, 'history.html', context)

@rate_limit(limit=60, window=60)
@login_required
def recurring_view(request):
    user = request.user
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            new_type = strip_tags(request.POST.get('type', ''))
            name = strip_tags(request.POST.get('name', ''))[:100]
            account = strip_tags(request.POST.get('account', 'Bank Account'))[:100]
            payment_method = strip_tags(request.POST.get('paymentMethod', 'Bank Transfer'))[:100]
            try:
                amount = float(request.POST.get('amount', 0))
            except (ValueError, TypeError):
                amount = 0.0
            
            try:
                execution_day = int(request.POST.get('executionDay', 1))
                execution_day = max(1, min(31, execution_day))
            except (ValueError, TypeError):
                execution_day = 1

            if amount > 0:
                if new_type == 'income':
                    RecurringIncome.objects.create(user=user, name=name, amount=amount, account=account, payment_method=payment_method, execution_day=execution_day)
                elif new_type == 'expense':
                    RecurringExpense.objects.create(user=user, name=name, amount=amount, account=account, payment_method=payment_method, execution_day=execution_day)
            recalculate_current_month(user)
        elif action == 'recalculate':
            recalculate_current_month(user)
        return redirect('recurring')
        
    incomes = RecurringIncome.objects.filter(user=user).order_by('-created_at')
    expenses = RecurringExpense.objects.filter(user=user).order_by('-created_at')
    
    context = {
        'recurring_incomes': incomes,
        'recurring_expenses': expenses
    }
    return render(request, 'recurring.html', context)

@rate_limit(limit=60, window=60)
@login_required
def groups_view(request):
    user = request.user
    
    if request.method == 'POST':
        name = strip_tags(request.POST.get('name', ''))[:100]
        description = strip_tags(request.POST.get('description', ''))[:500]
        icon = strip_tags(request.POST.get('icon', 'users'))[:50]
        icon_base64 = request.POST.get('icon_base64')
        
        if not name:
            return redirect('groups')
            
        # Create group and add creator as member
        group = Group.objects.create(name=name, description=description, icon=icon, created_by=user, icon_base64=icon_base64)
        GroupMember.objects.create(group=group, user=user, role='ADMIN')
        return redirect('group_detail', group_id=group.id)
        
    memberships = GroupMember.objects.filter(user=user).select_related('group')
    groups = [m.group for m in memberships]
    
    context = {
        'groups': groups
    }
    return render(request, 'groups.html', context)

@rate_limit(limit=60, window=60)
@login_required
def group_detail_view(request, group_id):
    user = request.user
    group = get_object_or_404(Group, id=group_id)
    
    # Verify membership and get role
    membership = GroupMember.objects.filter(group=group, user=user).first()
    if not membership:
        return render(request, '403.html', status=403)
    user_role = membership.role
        
    error_message = None
    # Handle adding new member
    if request.method == 'POST' and 'new_member_email' in request.POST:
        if user_role != 'ADMIN':
            error_message = "Only Admins can add members."
        else:
            email = strip_tags(request.POST.get('new_member_email', '')).strip()[:200]
            to_add = get_object_or_none(User, email=email)
            if to_add:
                GroupMember.objects.get_or_create(group=group, user=to_add)
                return redirect('group_detail', group_id=group.id)
            else:
                error_message = f"User with email '{email}' not found."
        
    memberships = GroupMember.objects.filter(group=group).select_related('user', 'user__profile')
    members = [m.user for m in memberships]
    
    expenses = GroupExpense.objects.filter(group=group).select_related('paid_by').prefetch_related('payments__user', 'splits__user').order_by('-date')
    settlements = Settlement.objects.filter(group=group).select_related('from_user', 'to_user').order_by('-date')
    
    # Compute Net Balances
    net_balances = {m.id: 0.0 for m in members}
    
    for exp in expenses:
        payments = exp.payments.all()
        if payments.exists():
            for pmt in payments:
                if pmt.user_id in net_balances:
                    net_balances[pmt.user_id] += pmt.amount
        elif exp.paid_by_id:
            # Fallback for old data
            if exp.paid_by_id in net_balances:
                net_balances[exp.paid_by_id] += exp.amount
                
        for split in exp.splits.all():
            if split.user_id in net_balances:
                net_balances[split.user_id] -= split.amount
                
    for setl in settlements:
        if setl.from_user_id in net_balances:
            net_balances[setl.from_user_id] += setl.amount
        if setl.to_user_id in net_balances:
            net_balances[setl.to_user_id] -= setl.amount
            
    balances_list = []
    for m in members:
        net_val = round(net_balances[m.id], 2)
        balances_list.append({
            'userId': m.id,
            'name': m.first_name if m.first_name else m.username,
            'email': m.email,
            'net': net_val,
            'abs_net': abs(net_val)
        })
        
    # Debt Simplification Greedy Algorithm
    debtors = [b for b in balances_list if b['net'] < -0.01]
    creditors = [b for b in balances_list if b['net'] > 0.01]
    
    debtors.sort(key=lambda x: x['net']) # largest debt first
    creditors.sort(key=lambda x: x['net'], reverse=True) # largest credit first
    
    simplified_debts = []
    d_idx = 0
    c_idx = 0
    
    # Deep copy lists for greedy processing
    debtors_cp = [dict(d) for d in debtors]
    creditors_cp = [dict(c) for c in creditors]
    
    while d_idx < len(debtors_cp) and c_idx < len(creditors_cp):
        debtor = debtors_cp[d_idx]
        creditor = creditors_cp[c_idx]
        
        debt_amount = abs(debtor['net'])
        credit_amount = creditor['net']
        
        settled_amount = min(debt_amount, credit_amount)
        
        creditor_user = User.objects.filter(id=creditor['userId']).first()
        creditor_active_upi = MemberUpiId.objects.filter(user=creditor_user, is_active=True).first()
        creditor_upi_str = creditor_active_upi.upi_id if creditor_active_upi else ""

        simplified_debts.append({
            'fromUserId': debtor['userId'],
            'fromUserName': debtor['name'],
            'toUserId': creditor['userId'],
            'toUserName': creditor['name'],
            'amount': round(settled_amount, 2),
            'toUserActiveUpi': creditor_upi_str
        })
        
        debtor['net'] += settled_amount
        creditor['net'] -= settled_amount
        
        if abs(debtor['net']) < 0.01:
            d_idx += 1
        if abs(creditor['net']) < 0.01:
            c_idx += 1
            
    # Compute Analytics
    total_spend = sum(exp.amount for exp in expenses)
    contributions = {m.id: 0.0 for m in members}
    for exp in expenses:
        payments = exp.payments.all()
        if payments.exists():
            for pmt in payments:
                if pmt.user_id in contributions:
                    contributions[pmt.user_id] += pmt.amount
        else:
            if exp.paid_by_id in contributions:
                contributions[exp.paid_by_id] += exp.amount
        
    sorted_contribs = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
    highest_contrib_name = "N/A"
    if sorted_contribs and sorted_contribs[0][1] > 0:
        contrib_user = get_object_or_none(User, id=sorted_contribs[0][0])
        if contrib_user:
            highest_contrib_name = f"{contrib_user.first_name if contrib_user.first_name else contrib_user.username} (₹{round(sorted_contribs[0][1], 2)})"
            
    sorted_debtors = sorted(balances_list, key=lambda x: x['net'])
    highest_debtor_name = "None"
    if sorted_debtors and sorted_debtors[0]['net'] < -0.01:
        highest_debtor_name = f"{sorted_debtors[0]['name']} (owes ₹{abs(sorted_debtors[0]['net'])})"
        
    # Category parsing from descriptions
    category_spend = {}
    for exp in expenses:
        desc = exp.description.lower()
        category = "Others"
        if any(w in desc for w in ["food", "grocery", "dinner", "lunch", "restaurant", "cafe"]):
            category = "Food"
        elif any(w in desc for w in ["travel", "cab", "trip", "fuel", "car", "flight"]):
            category = "Travel"
        elif any(w in desc for w in ["rent", "flat", "room"]):
            category = "Rent"
        elif any(w in desc for w in ["electricity", "bill", "water", "utility"]):
            category = "Utilities"
        elif any(w in desc for w in ["movie", "concert", "show", "party", "entertainment"]):
            category = "Entertainment"
        elif any(w in desc for w in ["shop", "clothes", "shoes", "mall"]):
            category = "Shopping"
            
        category_spend[category] = category_spend.get(category, 0) + exp.amount
        
    category_breakdown = []
    pie_categories = []
    pie_values = []
    for name, val in category_spend.items():
        percentage = round((val / total_spend) * 100, 1) if total_spend > 0 else 0
        category_breakdown.append({
            'name': name,
            'value': round(val, 2),
            'percentage': percentage
        })
        pie_categories.append(name)
        pie_values.append(val)
        
    # Generate Analytics Charts using Matplotlib/Seaborn
    category_pie_chart = generate_spending_pie_chart(pie_categories, pie_values)
    
    standing_names = [b['name'] for b in balances_list]
    standing_nets = [b['net'] for b in balances_list]
    net_standing_chart = generate_group_net_standing_chart(standing_names, standing_nets)
    
    total_settled = sum(setl.amount for setl in settlements)
    settlement_ratio = round(total_settled / total_spend, 2) if total_spend > 0 else 0.0
    
    active_tab = strip_tags(request.GET.get('tab', 'ledger'))[:50] # ledger, balances, analytics
    
    extended_members = []
    for m in memberships:
        net_val = round(net_balances[m.user.id], 2)
        profile_pic = None
        if hasattr(m.user, 'profile'):
            profile_pic = m.user.profile.avatar_base64 or m.user.profile.avatar
        active_upi = MemberUpiId.objects.filter(user=m.user, is_active=True).first()
        active_upi_str = active_upi.upi_id if active_upi else ""

        extended_members.append({
            'id': m.user.id,
            'name': m.user.first_name if m.user.first_name else m.user.username,
            'email': m.user.email,
            'role': m.role,
            'joined_at': m.joined_at,
            'net': net_val,
            'abs_net': abs(net_val),
            'profile_pic': profile_pic,
            'active_upi': active_upi_str
        })
        
    # --- Expense History Logic ---
    history_expenses = expenses
    search_query = strip_tags(request.GET.get('search', '').strip())[:100]
    category_filter = strip_tags(request.GET.get('category', 'All'))[:50]

    if search_query:
        history_expenses = history_expenses.filter(Q(description__icontains=search_query) | Q(category__icontains=search_query))
    if category_filter != 'All':
        history_expenses = history_expenses.filter(category=category_filter)

    categories = ["Income", "Food", "Travel", "Shopping", "Entertainment", "Rent", "Utilities", "Health", "Education", "Investment", "Others"]

    from collections import defaultdict
    from datetime import datetime
    grouped_data = defaultdict(list)
    for exp in history_expenses:
        key = exp.date.strftime("%Y-%m")
        grouped_data[key].append(exp)

    grouped_months = []
    CATEGORY_COLORS = {
        "Food": "#34d399", "Travel": "#fb7185", "Shopping": "#fbbf24",
        "Entertainment": "#a78bfa", "Rent": "#22d3ee", "Utilities": "#f472b6",
        "Health": "#a7f3d0", "Education": "#c084fc", "Investment": "#818cf8",
        "Others": "#94a3b8"
    }

    for key in sorted(grouped_data.keys(), reverse=True):
        exps = grouped_data[key]
        year, month = map(int, key.split('-'))
        label = datetime(year, month, 1).strftime("%B %Y")
        
        total_month_spend = sum(e.amount for e in exps if e.category != "Income")
        total_month_income = sum(e.amount for e in exps if e.category == "Income")
        
        category_sums = {}
        for e in exps:
            if e.category != "Income":
                category_sums[e.category] = category_sums.get(e.category, 0) + e.amount
                
        breakdown = []
        for cat_name, cat_val in category_sums.items():
            breakdown.append({
                'name': cat_name,
                'amount': cat_val,
                'color': CATEGORY_COLORS.get(cat_name, '#94a3b8')
            })
            
        grouped_months.append({
            'key': key,
            'label': label,
            'expenses': exps,
            'total_spend': total_month_spend,
            'total_income': total_month_income,
            'category_breakdown': breakdown
        })
        
    import json as _json

    # Serialize settlements for Settlement Score widget (no new queries — reuses fetched querysets)
    settlements_data = []
    for s in settlements:
        settlements_data.append({
            'from_user_id': s.from_user_id,
            'to_user_id': s.to_user_id,
            'amount': float(s.amount),
            'date': s.date.strftime('%Y-%m-%d') if s.date else '',
            'is_settled': s.is_settled,
        })

    # Serialize expenses with splits for Settlement Score widget (reuses prefetched splits)
    expenses_score_data = []
    for exp in expenses:
        splits_data = []
        for sp in exp.splits.all():
            splits_data.append({
                'user_id': sp.user_id,
                'amount': float(sp.amount),
                'is_settled': sp.is_settled,
            })
        payments_data = []
        for pmt in exp.payments.all():
            payments_data.append({
                'user_id': pmt.user_id,
                'amount': float(pmt.amount),
            })
        expenses_score_data.append({
            'id': exp.id,
            'date': exp.date.strftime('%Y-%m-%d') if exp.date else '',
            'amount': float(exp.amount),
            'paid_by_id': exp.paid_by_id,
            'splits': splits_data,
            'payments': payments_data,
        })

    # Serialize members for Settlement Score widget
    members_score_data = []
    for m in memberships:
        profile_pic = None
        if hasattr(m.user, 'profile'):
            profile_pic = m.user.profile.avatar_base64 or m.user.profile.avatar or None
        members_score_data.append({
            'id': m.user.id,
            'name': m.user.first_name if m.user.first_name else m.user.username,
            'role': m.role,
            'profile_pic': profile_pic,
        })

    context = {
        'group': group,
        'user_role': user_role,
        'members': members,
        'extended_members': extended_members,
        'expenses': expenses,
        'settlements': settlements,
        'balances': balances_list,
        'debts': simplified_debts,
        'total_spend': total_spend,
        'highest_contributor': highest_contrib_name,
        'highest_debtor': highest_debtor_name,
        'category_breakdown': category_breakdown,
        'category_pie_chart': category_pie_chart,
        'net_standing_chart': net_standing_chart,
        'total_settled': total_settled,
        'settlement_ratio': settlement_ratio,
        'active_tab': active_tab,
        'grouped_months': grouped_months,
        'categories': categories,
        'search_query': search_query,
        'selected_category': category_filter,
        'error': error_message,
        'settlements_json': _json.dumps(settlements_data),
        'expenses_score_json': _json.dumps(expenses_score_data),
        'members_score_json': _json.dumps(members_score_data),
    }
    return render(request, 'group_detail.html', context)

@rate_limit(limit=60, window=60)
@login_required
def profile_view(request):
    user = request.user
    profile = user.profile
    
    if request.method == 'POST':
        # Handle avatar removal
        if request.POST.get('remove_avatar') == 'true':
            profile.avatar = ''
            profile.avatar_base64 = ''
            
        selected_avatar = strip_tags(request.POST.get('avatar', ''))
        if selected_avatar and selected_avatar.startswith('avatar-'):
            profile.avatar = selected_avatar[:255]
            
        avatar_base64 = request.POST.get('avatar_base64')
        if avatar_base64:
            profile.avatar_base64 = avatar_base64

        profile.phone = strip_tags(request.POST.get('phone', ''))[:20]
        profile.bio = strip_tags(request.POST.get('bio', ''))[:500]
        profile.country = strip_tags(request.POST.get('country', 'India'))[:100]
        profile.save()
        
        user.first_name = strip_tags(request.POST.get('name', user.first_name))[:150]
        user.save()
        return redirect('profile')
        
    context = {
        'profile': profile
    }
    return render(request, 'profile.html', context)

@rate_limit(limit=30, window=60)
@login_required
def add_expense_api(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            try:
                amount = float(body.get('amount'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid amount.'}, status=400)
                
            if amount <= 0:
                return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)
            category = strip_tags(body.get('category', ''))[:50]
            account = strip_tags(body.get('account', 'Bank Account'))[:50]
            payment_method = strip_tags(body.get('paymentMethod', ''))[:50]
            description = strip_tags(body.get('description', ''))[:250]
            date_str = strip_tags(body.get('date', ''))[:20]
            
            if account == 'Cash':
                payment_method = 'Cash'
            elif account == 'Credit Card':
                payment_method = 'Credit Card'
            elif account == 'Bank Account' and payment_method not in ['UPI', 'Debit Card', 'Bank Transfer']:
                payment_method = 'UPI'
            
            txn_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
            txn_date = django_timezone.make_aware(txn_date)
            
            now = django_timezone.now()
                
            expense = PersonalExpense.objects.create(
                user=request.user,
                amount=amount,
                category=category,
                payment_method=payment_method,
                account=account,
                description=description,
                date=txn_date,
                month=txn_date.month,
                year=txn_date.year
            )
            return JsonResponse({'id': expense.id, 'status': 'success'}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        except Exception as e:
            logger.error(f"SECURITY: API Exception in {request.path} by user {request.user.id if request.user.is_authenticated else 'Anonymous'}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def edit_expense_api(request, expense_id):
    if request.method == 'POST' or request.method == 'PUT':
        try:
            expense = get_object_or_404(PersonalExpense, id=expense_id, user=request.user)
            body = json.loads(request.body)
            try:
                amount = float(body.get('amount'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid amount.'}, status=400)
                
            if amount <= 0:
                return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)
            category = strip_tags(body.get('category', ''))[:50]
            account = strip_tags(body.get('account', 'Bank Account'))[:50]
            payment_method = strip_tags(body.get('paymentMethod', ''))[:50]
            description = strip_tags(body.get('description', ''))[:250]
            date_str = strip_tags(body.get('date', ''))[:20]
            
            if account == 'Cash':
                payment_method = 'Cash'
            elif account == 'Credit Card':
                payment_method = 'Credit Card'
            elif account == 'Bank Account' and payment_method not in ['UPI', 'Debit Card', 'Bank Transfer']:
                payment_method = 'UPI'
            
            txn_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
            txn_date = django_timezone.make_aware(txn_date)
            
            expense.amount = amount
            expense.category = category
            expense.payment_method = payment_method
            expense.account = account
            expense.description = description
            expense.date = txn_date
            expense.month = txn_date.month
            expense.year = txn_date.year
            expense.save()
            
            recalculate_current_month(request.user)
            return JsonResponse({'status': 'success'})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        except Exception as e:
            logger.error(f"SECURITY: API Exception in {request.path} by user {request.user.id if request.user.is_authenticated else 'Anonymous'}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST or PUT required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def delete_expense_api(request, expense_id):
    if request.method == 'POST' or request.method == 'DELETE':
        expense = get_object_or_404(PersonalExpense, id=expense_id, user=request.user)
        expense.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'POST or DELETE required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def delete_recurring_api(request, item_id, item_type):
    if request.method == 'POST' or request.method == 'DELETE':
        if item_type == 'income':
            item = get_object_or_404(RecurringIncome, id=item_id, user=request.user)
        elif item_type == 'expense':
            item = get_object_or_404(RecurringExpense, id=item_id, user=request.user)
        else:
            return JsonResponse({'error': 'Invalid type'}, status=400)
            
        item.delete()
        recalculate_current_month(request.user)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'POST or DELETE required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def edit_recurring_api(request, item_id, item_type):
    if request.method == 'POST' or request.method == 'PUT':
        try:
            body = json.loads(request.body)
            name = strip_tags(body.get('name', ''))[:100]
            account = strip_tags(body.get('account', 'Bank Account'))[:100]
            payment_method = strip_tags(body.get('paymentMethod', 'Bank Transfer'))[:100]
            try:
                amount = float(body.get('amount'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid amount.'}, status=400)
            
            try:
                execution_day = int(body.get('executionDay', 1))
                execution_day = max(1, min(31, execution_day))
            except (ValueError, TypeError):
                execution_day = 1
            
            if item_type == 'income':
                item = get_object_or_404(RecurringIncome, id=item_id, user=request.user)
            elif item_type == 'expense':
                item = get_object_or_404(RecurringExpense, id=item_id, user=request.user)
            else:
                return JsonResponse({'error': 'Invalid type'}, status=400)
                
            item.name = name
            item.amount = amount
            item.account = account
            item.payment_method = payment_method
            item.execution_day = execution_day
            item.save()
            
            recalculate_current_month(request.user)
            return JsonResponse({'status': 'success'})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        except Exception as e:
            logger.error(f"SECURITY: API Exception in {request.path} by user {request.user.id if request.user.is_authenticated else 'Anonymous'}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def get_upi_ids_api(request):
    upi_ids = MemberUpiId.objects.filter(user=request.user)
    data = []
    for item in upi_ids:
        data.append({
            'id': item.id,
            'upi_id': item.upi_id,
            'nickname': item.nickname or '',
            'is_active': item.is_active
        })
    return JsonResponse({'upi_ids': data})

@rate_limit(limit=30, window=60)
@login_required
def add_upi_id_api(request):
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            upi_id = strip_tags(payload.get('upi_id', '')).strip()
            nickname = strip_tags(payload.get('nickname', '')).strip()

            # Format validation
            import re
            if not re.match(r'^[\w.\-_]+@[\w]+$', upi_id):
                return JsonResponse({'error': 'Invalid UPI ID format. E.g. example@oksbi, example@ybl'}, status=400)

            count = MemberUpiId.objects.filter(user=request.user).count()
            is_active = (count == 0)

            new_upi = MemberUpiId.objects.create(
                user=request.user,
                upi_id=upi_id,
                nickname=nickname,
                is_active=is_active
            )
            return JsonResponse({'status': 'success', 'upi_id': {
                'id': new_upi.id,
                'upi_id': new_upi.upi_id,
                'nickname': new_upi.nickname or '',
                'is_active': new_upi.is_active
            }})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def set_active_upi_api(request, upi_id):
    if request.method == 'POST':
        try:
            target = get_object_or_404(MemberUpiId, id=upi_id, user=request.user)
            MemberUpiId.objects.filter(user=request.user).update(is_active=False)
            target.is_active = True
            target.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def delete_upi_api(request, upi_id):
    if request.method == 'POST' or request.method == 'DELETE':
        try:
            target = get_object_or_404(MemberUpiId, id=upi_id, user=request.user)
            was_active = target.is_active
            target.delete()

            if was_active:
                next_upi = MemberUpiId.objects.filter(user=request.user).first()
                if next_upi:
                    next_upi.is_active = True
                    next_upi.save()

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST/DELETE required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def add_group_expense_api(request, group_id):
    if request.method == 'POST':
        try:
            group = get_object_or_404(Group, id=group_id)
            if not GroupMember.objects.filter(group=group, user=request.user).exists():
                logger.warning(f"SECURITY: Unauthorized group access attempt by user {request.user.id}.")
                return JsonResponse({'error': 'Unauthorized: You are not a member of this group'}, status=403)
            body = json.loads(request.body)
            
            try:
                amount = float(body.get('amount'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid amount.'}, status=400)
                
            description = strip_tags(body.get('description', ''))[:250]
            payers = body.get('payers', []) # list of {userId, amount}
            payment_method = strip_tags(body.get('paymentMethod', 'UPI'))[:50]
            split_type = strip_tags(body.get('splitType', 'EQUAL'))[:50]
            splits_data = body.get('splits', []) # list of {userId, amount}
            date_str = strip_tags(body.get('date', ''))[:20]
            
            if amount <= 0:
                return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)
            if not payers:
                return JsonResponse({'error': 'At least one payer is required.'}, status=400)
            if not splits_data:
                return JsonResponse({'error': 'At least one person must be involved in the split to avoid division by zero.'}, status=400)
                
            # IDOR check: Verify all participants are in the group
            participant_ids = set([int(p['userId']) for p in payers] + [int(s['userId']) for s in splits_data])
            valid_member_ids = set(GroupMember.objects.filter(group=group).values_list('user_id', flat=True))
            for uid in participant_ids:
                if uid not in valid_member_ids:
                    logger.warning(f"SECURITY: IDOR blocked! User {request.user.id} attempted to link non-members to a transaction.")
                    return JsonResponse({'error': 'One or more users involved in this transaction are not members of the group.'}, status=400)
                    
            total_paid_cents = sum(round(float(p['amount']) * 100) for p in payers)
            amount_cents = round(amount * 100)
            
            if abs(total_paid_cents - amount_cents) > 5:
                return JsonResponse({'error': f'Sum of payments must equal total amount.'}, status=400)
            elif total_paid_cents != amount_cents and len(payers) > 0:
                diff_cents = amount_cents - total_paid_cents
                payers[0]['amount'] = float(round(float(payers[0]['amount']) * 100) + diff_cents) / 100.0
            
            txn_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
            txn_date = django_timezone.make_aware(txn_date)
            
            first_payer = get_object_or_404(User, id=payers[0]['userId'])
            
            desc_lower = description.lower()
            guessed_category = "Others"
            if any(w in desc_lower for w in ["food", "grocery", "dinner", "lunch", "restaurant", "cafe"]):
                guessed_category = "Food"
            elif any(w in desc_lower for w in ["travel", "cab", "trip", "fuel", "car", "flight"]):
                guessed_category = "Travel"
            elif any(w in desc_lower for w in ["rent", "flat", "room"]):
                guessed_category = "Rent"
            elif any(w in desc_lower for w in ["electricity", "bill", "water", "utility"]):
                guessed_category = "Utilities"
            elif any(w in desc_lower for w in ["movie", "concert", "show", "party", "entertainment"]):
                guessed_category = "Entertainment"
            elif any(w in desc_lower for w in ["shop", "clothes", "shoes", "mall"]):
                guessed_category = "Shopping"
                
            # Create group expense
            group_expense = GroupExpense.objects.create(
                group=group,
                paid_by=first_payer, # fallback for older records
                amount=amount,
                description=description,
                category=strip_tags(body.get('category', '')).strip() or guessed_category,
                date=txn_date
            )
            
            # Create GroupExpensePayment records
            for p in payers:
                u = get_object_or_404(User, id=p['userId'])
                GroupExpensePayment.objects.create(
                    group_expense=group_expense,
                    user=u,
                    amount=float(p['amount'])
                )
            
            # Create splits
            if split_type == 'EQUAL':
                allocated_cents = 0
                for i, s in enumerate(splits_data):
                    u = get_object_or_404(User, id=s['userId'])
                    if i == len(splits_data) - 1:
                        share_cents = amount_cents - allocated_cents
                    else:
                        share_cents = round(amount_cents / len(splits_data))
                        allocated_cents += share_cents
                    GroupExpenseSplit.objects.create(
                        group_expense=group_expense,
                        user=u,
                        amount=share_cents / 100.0
                    )
            elif split_type == 'EXACT':
                total_split_cents = sum(round(float(s['amount']) * 100) for s in splits_data)
                if abs(total_split_cents - amount_cents) <= 5 and total_split_cents != amount_cents and len(splits_data) > 0:
                    diff_cents = amount_cents - total_split_cents
                    splits_data[0]['amount'] = float(round(float(splits_data[0]['amount']) * 100) + diff_cents) / 100.0
                
                for s in splits_data:
                    u = get_object_or_404(User, id=s['userId'])
                    GroupExpenseSplit.objects.create(
                        group_expense=group_expense,
                        user=u,
                        amount=float(s['amount'])
                    )
            elif split_type == 'PERCENTAGE':
                allocated_cents = 0
                for i, s in enumerate(splits_data):
                    u = get_object_or_404(User, id=s['userId'])
                    if i == len(splits_data) - 1:
                        share_cents = amount_cents - allocated_cents
                    else:
                        share_cents = round((float(s['percentage']) / 100.0) * amount_cents)
                        allocated_cents += share_cents
                    GroupExpenseSplit.objects.create(
                        group_expense=group_expense,
                        user=u,
                        amount=share_cents / 100.0
                    )
                    
            return JsonResponse({'status': 'success'}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        except Exception as e:
            logger.error(f"SECURITY: API Exception in {request.path} by user {request.user.id if request.user.is_authenticated else 'Anonymous'}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def edit_group_expense_api(request, group_id, expense_id):
    if request.method == 'POST' or request.method == 'PUT':
        try:
            group = get_object_or_404(Group, id=group_id)
            if not GroupMember.objects.filter(group=group, user=request.user).exists():
                logger.warning(f"SECURITY: Unauthorized group access attempt by user {request.user.id}.")
                return JsonResponse({'error': 'Unauthorized: You are not a member of this group'}, status=403)
            group_expense = get_object_or_404(GroupExpense, id=expense_id, group=group)
            body = json.loads(request.body)
            
            try:
                amount = float(body.get('amount'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid amount.'}, status=400)
                
            description = strip_tags(body.get('description', ''))[:250]
            payers = body.get('payers', [])
            split_type = strip_tags(body.get('splitType', 'EQUAL'))[:50]
            splits_data = body.get('splits', [])
            date_str = strip_tags(body.get('date', ''))[:20]
            
            if amount <= 0:
                return JsonResponse({'error': 'Amount must be greater than zero.'}, status=400)
            if not payers:
                return JsonResponse({'error': 'At least one payer is required.'}, status=400)
            if not splits_data:
                return JsonResponse({'error': 'At least one person must be involved in the split to avoid division by zero.'}, status=400)
                
            # IDOR check: Verify all participants are in the group
            participant_ids = set([int(p['userId']) for p in payers] + [int(s['userId']) for s in splits_data])
            valid_member_ids = set(GroupMember.objects.filter(group=group).values_list('user_id', flat=True))
            for uid in participant_ids:
                if uid not in valid_member_ids:
                    logger.warning(f"SECURITY: IDOR blocked! User {request.user.id} attempted to link non-members to a transaction.")
                    return JsonResponse({'error': 'One or more users involved in this transaction are not members of the group.'}, status=400)
                    
            total_paid_cents = sum(round(float(p['amount']) * 100) for p in payers)
            amount_cents = round(amount * 100)
            
            if abs(total_paid_cents - amount_cents) > 5:
                return JsonResponse({'error': f'Sum of payments must equal total amount.'}, status=400)
            elif total_paid_cents != amount_cents and len(payers) > 0:
                diff_cents = amount_cents - total_paid_cents
                payers[0]['amount'] = float(round(float(payers[0]['amount']) * 100) + diff_cents) / 100.0
            
            txn_date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
            txn_date = django_timezone.make_aware(txn_date)
            
            first_payer = get_object_or_404(User, id=payers[0]['userId'])
            
            # Update expense object
            group_expense.amount = amount
            group_expense.description = description
            
            category = strip_tags(body.get('category', '')).strip()
            if not category:
                desc_lower = description.lower()
                guessed_category = "Others"
                if any(w in desc_lower for w in ["food", "grocery", "dinner", "lunch", "restaurant", "cafe"]):
                    guessed_category = "Food"
                elif any(w in desc_lower for w in ["travel", "cab", "trip", "fuel", "car", "flight"]):
                    guessed_category = "Travel"
                elif any(w in desc_lower for w in ["rent", "flat", "room"]):
                    guessed_category = "Rent"
                elif any(w in desc_lower for w in ["electricity", "bill", "water", "utility"]):
                    guessed_category = "Utilities"
                elif any(w in desc_lower for w in ["movie", "concert", "show", "party", "entertainment"]):
                    guessed_category = "Entertainment"
                elif any(w in desc_lower for w in ["shop", "clothes", "shoes", "mall"]):
                    guessed_category = "Shopping"
                category = guessed_category
                
            group_expense.category = category
            group_expense.date = txn_date
            group_expense.paid_by = first_payer
            group_expense.save()
            
            # Clear old payments and splits
            group_expense.payments.all().delete()
            group_expense.splits.all().delete()
            
            # Create new GroupExpensePayment records
            for p in payers:
                u = get_object_or_404(User, id=p['userId'])
                GroupExpensePayment.objects.create(
                    group_expense=group_expense,
                    user=u,
                    amount=float(p['amount'])
                )
            
            # Create new splits
            if split_type == 'EQUAL':
                allocated_cents = 0
                for i, s in enumerate(splits_data):
                    u = get_object_or_404(User, id=s['userId'])
                    if i == len(splits_data) - 1:
                        share_cents = amount_cents - allocated_cents
                    else:
                        share_cents = round(amount_cents / len(splits_data))
                        allocated_cents += share_cents
                    GroupExpenseSplit.objects.create(group_expense=group_expense, user=u, amount=share_cents / 100.0)
            elif split_type == 'EXACT':
                total_split_cents = sum(round(float(s['amount']) * 100) for s in splits_data)
                if abs(total_split_cents - amount_cents) <= 5 and total_split_cents != amount_cents and len(splits_data) > 0:
                    diff_cents = amount_cents - total_split_cents
                    splits_data[0]['amount'] = float(round(float(splits_data[0]['amount']) * 100) + diff_cents) / 100.0
                for s in splits_data:
                    u = get_object_or_404(User, id=s['userId'])
                    GroupExpenseSplit.objects.create(group_expense=group_expense, user=u, amount=float(s['amount']))
            elif split_type == 'PERCENTAGE':
                allocated_cents = 0
                for i, s in enumerate(splits_data):
                    u = get_object_or_404(User, id=s['userId'])
                    if i == len(splits_data) - 1:
                        share_cents = amount_cents - allocated_cents
                    else:
                        share_cents = round((float(s['percentage']) / 100.0) * amount_cents)
                        allocated_cents += share_cents
                    GroupExpenseSplit.objects.create(group_expense=group_expense, user=u, amount=share_cents / 100.0)
                    
            return JsonResponse({'status': 'success'})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        except Exception as e:
            logger.error(f"SECURITY: API Exception in {request.path} by user {request.user.id if request.user.is_authenticated else 'Anonymous'}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST or PUT required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def add_settlement_api(request, group_id):
    if request.method == 'POST':
        try:
            group = get_object_or_404(Group, id=group_id)
            if not GroupMember.objects.filter(group=group, user=request.user).exists():
                logger.warning(f"SECURITY: Unauthorized group access attempt by user {request.user.id}.")
                return JsonResponse({'error': 'Unauthorized: You are not a member of this group'}, status=403)
            body = json.loads(request.body)
            
            from_user_id = int(body.get('fromUserId'))
            to_user_id = int(body.get('toUserId'))
            try:
                amount = float(body.get('amount'))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid amount.'}, status=400)
            if amount <= 0:
                return JsonResponse({'error': 'Settlement amount must be greater than zero.'}, status=400)
            
            # IDOR check: Verify both users are members of the group
            valid_member_ids = set(GroupMember.objects.filter(group=group).values_list('user_id', flat=True))
            if from_user_id not in valid_member_ids or to_user_id not in valid_member_ids:
                logger.warning(f"SECURITY: IDOR blocked! User {request.user.id} attempted to settle with non-members.")
                return JsonResponse({'error': 'One or both users are not members of the group.'}, status=400)
                
            from_user = get_object_or_404(User, id=from_user_id)
            to_user = get_object_or_404(User, id=to_user_id)
            
            Settlement.objects.create(
                group=group,
                from_user=from_user,
                to_user=to_user,
                amount=amount,
                is_settled=True
            )
            return JsonResponse({'status': 'success'}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)
        except Exception as e:
            logger.error(f"SECURITY: API Exception in {request.path} by user {request.user.id if request.user.is_authenticated else 'Anonymous'}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=30, window=60)


@rate_limit(limit=10, window=60)
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        name = strip_tags(request.POST.get('name', ''))[:100]
        email = strip_tags(request.POST.get('email', '')).strip()[:200]
        password = request.POST.get('password')
        confirm_pass = request.POST.get('confirm_password')
        
        if password != confirm_pass:
            return render(request, 'register.html', {'error': 'Passwords do not match'})
            
        if User.objects.filter(email=email).exists() or User.objects.filter(username=email).exists():
            return render(request, 'register.html', {'error': 'User with this email already exists'})
            
        # Enforce password policies
        try:
            validate_password(password)
        except ValidationError as e:
            return render(request, 'register.html', {'error': '\n'.join(e.messages)})
            
        user = User.objects.create_user(username=email, email=email, password=password)
        user.first_name = name
        user.is_active = True # Bypass email activation on Render Free
        user.save()
        
        # Save phone and avatar to user profile
        phone = strip_tags(request.POST.get('phone', '')).strip()[:50]
        avatar_base64 = request.POST.get('avatar_base64', '')
        if phone:
            user.profile.phone = phone
        if avatar_base64:
            user.profile.avatar_base64 = avatar_base64
        user.profile.save()
        
        login(request, user)
        return redirect('dashboard')
    return render(request, 'register.html')

def activate_account(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        return redirect('dashboard')
    else:
        return render(request, 'login.html', {'error': 'Activation link is invalid or has expired.'})

@rate_limit(limit=10, window=60)
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email = strip_tags(request.POST.get('email', '')).strip()[:200]
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            logger.warning(f"SECURITY: Successful login for {email}.")
            return redirect('dashboard')
        else:
            # Check if it failed because the user is inactive
            user_obj = get_object_or_none(User, username=email)
            if user_obj and not user_obj.is_active and user_obj.check_password(password):
                return render(request, 'login.html', {'error': 'Account is not activated. Please check your email inbox for the activation link.'})
                
            logger.warning(f"SECURITY: Failed login attempt for {email}.")
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@rate_limit(limit=30, window=60)
@login_required
def delete_group_expense_api(request, group_id, expense_id):
    if request.method == 'POST' or request.method == 'DELETE':
        group = get_object_or_404(Group, id=group_id)
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        expense = get_object_or_404(GroupExpense, id=expense_id, group=group)
        expense.delete()
        if not GroupExpense.objects.filter(group=group).exists():
            Settlement.objects.filter(group=group).delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'POST or DELETE required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def delete_settlement_api(request, group_id, settlement_id):
    if request.method == 'POST' or request.method == 'DELETE':
        group = get_object_or_404(Group, id=group_id)
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        settlement = get_object_or_404(Settlement, id=settlement_id, group=group)
        settlement.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'POST or DELETE required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def delete_group_api(request, group_id):
    if request.method == 'POST' or request.method == 'DELETE':
        group = get_object_or_404(Group, id=group_id)
        membership = GroupMember.objects.filter(group=group, user=request.user).first()
        if not membership or membership.role != 'ADMIN':
            logger.warning(f"SECURITY: Non-admin delete attempt on group by user {request.user.id}.")
            return JsonResponse({'error': 'Only Group Admins can delete this group.'}, status=403)
        group.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'POST or DELETE required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def edit_group_api(request, group_id):
    if request.method == 'POST':
        try:
            group = get_object_or_404(Group, id=group_id)
            membership = GroupMember.objects.filter(group=group, user=request.user).first()
            if not membership or membership.role != 'ADMIN':
                logger.warning(f"SECURITY: Non-admin edit attempt on group details by user {request.user.id}.")
                return JsonResponse({'error': 'Only Group Admins can edit group details.'}, status=403)
            
            # Handle both JSON (legacy) and FormData
            name = ''
            description = ''
            
            if request.content_type == 'application/json':
                body = json.loads(request.body)
                name = strip_tags(body.get('name', '')).strip()[:100]
                description = strip_tags(body.get('description', '')).strip()[:500]
                
                if body.get('remove_icon') == 'true':
                    group.icon = ''
                    group.icon_base64 = ''
                
                icon = body.get('icon')
                if icon:
                    group.icon = icon[:255]
                
                icon_base64 = body.get('icon_base64')
                if icon_base64:
                    group.icon_base64 = icon_base64
            else:
                name = strip_tags(request.POST.get('name', '')).strip()[:100]
                description = strip_tags(request.POST.get('description', '')).strip()[:500]

            if not name:
                return JsonResponse({'error': 'Group name is required'}, status=400)
                
            group.name = name
            group.description = description
            
            group.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            logger.error(f"SECURITY: API Exception in {request.path} by user {request.user.id if request.user.is_authenticated else 'Anonymous'}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

def get_user_group_balance(group, user_id):
    expenses = GroupExpense.objects.filter(group=group).prefetch_related('payments', 'splits')
    settlements = Settlement.objects.filter(group=group)
    net = 0.0
    
    for exp in expenses:
        for pmt in exp.payments.all():
            if pmt.user_id == user_id:
                net += pmt.amount
        if not exp.payments.exists() and exp.paid_by_id == user_id:
            net += exp.amount
            
        for split in exp.splits.all():
            if split.user_id == user_id:
                net -= split.amount
                
    for setl in settlements:
        if setl.from_user_id == user_id:
            net += setl.amount
        if setl.to_user_id == user_id:
            net -= setl.amount
            
    return round(net, 2)

@rate_limit(limit=30, window=60)
@login_required
def api_remove_member(request, group_id, member_id):
    if request.method == 'POST':
        group = get_object_or_404(Group, id=group_id)
        admin_membership = GroupMember.objects.filter(group=group, user=request.user).first()
        if not admin_membership or admin_membership.role != 'ADMIN':
            return JsonResponse({'error': 'Only Admins can remove members.'}, status=403)
            
        target_membership = get_object_or_404(GroupMember, group=group, user_id=member_id)
        
        balance = get_user_group_balance(group, member_id)
        if abs(balance) > 0.01:
            return JsonResponse({'error': f'This member cannot be removed until all balances are settled. Current balance: ₹{balance}'}, status=400)
            
        target_membership.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=30, window=60)
@login_required
def api_leave_group(request, group_id):
    if request.method == 'POST':
        group = get_object_or_404(Group, id=group_id)
        membership = get_object_or_404(GroupMember, group=group, user=request.user)
        
        balance = get_user_group_balance(group, request.user.id)
        if abs(balance) > 0.01:
            return JsonResponse({'error': f'Please settle all balances before leaving the group. Current balance: ₹{balance}'}, status=400)
            
        membership.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'error': 'POST required'}, status=405)

@rate_limit(limit=10, window=60)
@login_required
@require_POST
def api_change_password(request):
    try:
        body = json.loads(request.body)
        current_password = body.get('current_password', '')
        new_password = body.get('new_password', '')
        confirm_password = body.get('confirm_password', '')
        
        if not request.user.check_password(current_password):
            return JsonResponse({'status': 'error', 'message': 'Current password is incorrect.'})
            
        if new_password != confirm_password:
            return JsonResponse({'status': 'error', 'message': 'New passwords do not match.'})
            
        try:
            validate_password(new_password, request.user)
        except ValidationError as e:
            return JsonResponse({'status': 'error', 'message': ' '.join(e.messages)})
            
        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        
        return JsonResponse({'status': 'success', 'message': 'Password changed successfully.'})
    except Exception as e:
        logger.error(f"Password change error for {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'An error occurred while changing password.'})

@login_required
@require_http_methods(["POST", "DELETE"])
def api_delete_account(request):
    try:
        user = request.user
        # Django's cascade delete handles everything: personal expenses, recurring setups, groups created, memberships, splits.
        user.delete()
        logout(request)
        return JsonResponse({'status': 'success', 'message': 'Account deleted successfully.'})
    except Exception as e:
        logger.error(f"Error deleting account for {request.user.username}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'Failed to delete account. Please try again.'})

@login_required
def export_expenses_pdf(request):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from django.http import HttpResponse
    
    expenses = PersonalExpense.objects.filter(user=request.user).order_by('date')
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="expenzo_history_{request.user.username}_{datetime.now().strftime("%Y%m%d")}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#4F46E5'),
        alignment=0,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#6B7280'),
        spaceAfter=20
    )
    
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#374151')
    )
    
    cell_header_style = ParagraphStyle(
        'CellHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white
    )
    
    story.append(Paragraph("Expenzo - Expense History", title_style))
    story.append(Paragraph(f"Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M')} | User: {request.user.username}", subtitle_style))
    
    col_widths = [110, 150, 80, 80, 60, 60]
    
    table_data = [[
        Paragraph("Date", cell_header_style),
        Paragraph("Description", cell_header_style),
        Paragraph("Category", cell_header_style),
        Paragraph("Account", cell_header_style),
        Paragraph("Payment Method", cell_header_style),
        Paragraph("Amount", cell_header_style),
    ]]
    
    total_amount = 0.0
    for exp in expenses:
        amount = exp.amount
        total_amount += amount
        date_str = exp.date.strftime("%Y-%m-%d %H:%M")
        
        table_data.append([
            Paragraph(date_str, cell_style),
            Paragraph(exp.description, cell_style),
            Paragraph(exp.category, cell_style),
            Paragraph(exp.account, cell_style),
            Paragraph(exp.payment_method, cell_style),
            Paragraph(f"{amount:.2f}", cell_style),
        ])
        
    table_data.append([
        Paragraph("Total Spends/Income", ParagraphStyle('TotalText', parent=cell_style, fontName='Helvetica-Bold')),
        "", "", "", "",
        Paragraph(f"{total_amount:.2f}", ParagraphStyle('TotalVal', parent=cell_style, fontName='Helvetica-Bold')),
    ])
    
    t = Table(table_data, colWidths=col_widths)
    
    t_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E5E7EB')),
        ('SPAN', (0, -1), (4, -1)),
        ('ALIGN', (5, 0), (5, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#1F2937')),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor('#1F2937')),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
    ])
    
    for i in range(1, len(table_data) - 1):
        if i % 2 == 0:
            t_style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F9FAFB'))
            
    t.setStyle(t_style)
    story.append(t)
    
    doc.build(story)
    return response

@login_required
def export_expenses_excel(request):
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from django.http import HttpResponse
    
    expenses = PersonalExpense.objects.filter(user=request.user).order_by('date')
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expense History"
    ws.views.sheetView[0].showGridLines = True
    
    font_family = "Segoe UI"
    title_font = Font(name=font_family, size=16, bold=True, color="1F2937")
    header_font = Font(name=font_family, size=11, bold=True, color="FFFFFF")
    data_font = Font(name=font_family, size=11, color="374151")
    total_font = Font(name=font_family, size=11, bold=True, color="1F2937")
    
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin', color='E5E7EB'),
        right=Side(style='thin', color='E5E7EB'),
        top=Side(style='thin', color='E5E7EB'),
        bottom=Side(style='thin', color='E5E7EB')
    )
    double_bottom_border = Border(
        top=Side(style='thin', color='1F2937'),
        bottom=Side(style='double', color='1F2937')
    )
    
    headers = ["Date", "Description", "Category", "Account", "Payment Method", "Amount"]
    
    ws.append([])
    ws.append([f"Expenzo Expense History - {request.user.username}"])
    ws.cell(row=2, column=1).font = title_font
    ws.append([])
    
    ws.append(headers)
    header_row = 4
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center" if header != "Description" else "left", vertical="center")
        cell.border = thin_border
    
    total_amount = 0.0
    current_row = 5
    for idx, exp in enumerate(expenses):
        date_str = exp.date.strftime("%Y-%m-%d %H:%M")
        amount = exp.amount
        
        ws.append([
            date_str,
            exp.description,
            exp.category,
            exp.account,
            exp.payment_method,
            amount
        ])
        
        row_fill = zebra_fill if idx % 2 == 1 else None
        
        for col_idx in range(1, 7):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.font = data_font
            cell.border = thin_border
            if row_fill:
                cell.fill = row_fill
            
            if col_idx == 1:
                cell.alignment = Alignment(horizontal="center")
            elif col_idx == 6:
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = '#,##0.00'
                total_amount += amount
            else:
                cell.alignment = Alignment(horizontal="left")
                
        current_row += 1
        
    ws.append([])
    ws.append(["Total Spends/Income", "", "", "", "", total_amount])
    total_row = current_row + 1
    
    ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=5)
    total_label_cell = ws.cell(row=total_row, column=1)
    total_label_cell.font = total_font
    total_label_cell.alignment = Alignment(horizontal="right")
    
    total_val_cell = ws.cell(row=total_row, column=6)
    total_val_cell.font = total_font
    total_val_cell.alignment = Alignment(horizontal="right")
    total_val_cell.number_format = '#,##0.00'
    total_val_cell.border = double_bottom_border
    
    for col in ws.columns:
        max_len = 0
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        for cell in col:
            val = str(cell.value or '')
            if cell.row == 2:
                continue
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = f'attachment; filename="expenzo_history_{request.user.username}_{datetime.now().strftime("%Y%m%d")}.xlsx"'
    wb.save(response)
    return response

@login_required
def export_group_pdf(request, group_id):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404
    
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(user=request.user).exists():
        return HttpResponse("Unauthorized", status=403)
        
    expenses = group.expenses.all().order_by('date')
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="expenzo_group_{group.name}_{datetime.now().strftime("%Y%m%d")}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#4F46E5'),
        alignment=0,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#4B5563'),
        spaceAfter=15
    )
    
    header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.white
    )
    
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#374151')
    )
    
    total_style = ParagraphStyle(
        'TableTotal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#111827')
    )
    
    story.append(Paragraph(f"EXPENZO - {group.name}", title_style))
    story.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total expenses in the group splits.", subtitle_style))
    story.append(Spacer(1, 10))
    
    table_data = [[
        Paragraph('Date', header_style),
        Paragraph('Description', header_style),
        Paragraph('Category', header_style),
        Paragraph('Paid By', header_style),
        Paragraph('Amount', header_style)
    ]]
    
    total_amount = 0.0
    for exp in expenses:
        date_str = exp.date.strftime("%Y-%m-%d %H:%M")
        amount = exp.amount
        paid_by_str = exp.paid_by.username if exp.paid_by else "System"
        
        table_data.append([
            Paragraph(date_str, cell_style),
            Paragraph(exp.description, cell_style),
            Paragraph(exp.category, cell_style),
            Paragraph(paid_by_str, cell_style),
            Paragraph(f"INR {amount:.2f}", cell_style)
        ])
        total_amount += amount
        
    table_data.append([
        Paragraph('Total Spends', total_style),
        Paragraph('', total_style),
        Paragraph('', total_style),
        Paragraph('', total_style),
        Paragraph(f"INR {total_amount:.2f}", total_style)
    ])
    
    col_widths = [110, 160, 90, 90, 90]
    t = Table(table_data, colWidths=col_widths)
    t_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E5E7EB')),
        ('SPAN', (0, -1), (3, -1)),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#1F2937')),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor('#1F2937')),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
    ])
    
    for i in range(1, len(table_data) - 1):
        if i % 2 == 0:
            t_style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F9FAFB'))
            
    t.setStyle(t_style)
    story.append(t)
    
    doc.build(story)
    return response

@login_required
def export_group_excel(request, group_id):
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404
    
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(user=request.user).exists():
        return HttpResponse("Unauthorized", status=403)
        
    expenses = group.expenses.all().order_by('date')
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Group Splits"
    ws.views.sheetView[0].showGridLines = True
    
    font_family = "Segoe UI"
    title_font = Font(name=font_family, size=16, bold=True, color="1F2937")
    header_font = Font(name=font_family, size=11, bold=True, color="FFFFFF")
    data_font = Font(name=font_family, size=11, color="374151")
    total_font = Font(name=font_family, size=11, bold=True, color="1F2937")
    
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin', color='E5E7EB'),
        right=Side(style='thin', color='E5E7EB'),
        top=Side(style='thin', color='E5E7EB'),
        bottom=Side(style='thin', color='E5E7EB')
    )
    double_bottom_border = Border(
        top=Side(style='thin', color='1F2937'),
        bottom=Side(style='double', color='1F2937')
    )
    
    headers = ["Date", "Description", "Category", "Paid By", "Amount"]
    
    ws.append([])
    ws.append([f"Expenzo Group splits - {group.name}"])
    ws.cell(row=2, column=1).font = title_font
    ws.append([])
    
    ws.append(headers)
    header_row = 4
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center" if header != "Description" else "left", vertical="center")
        cell.border = thin_border
    
    total_amount = 0.0
    current_row = 5
    for idx, exp in enumerate(expenses):
        date_str = exp.date.strftime("%Y-%m-%d %H:%M")
        amount = exp.amount
        paid_by_str = exp.paid_by.username if exp.paid_by else "System"
        
        ws.append([
            date_str,
            exp.description,
            exp.category,
            paid_by_str,
            amount
        ])
        
        row_fill = zebra_fill if idx % 2 == 1 else None
        
        for col_idx in range(1, 6):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.font = data_font
            cell.border = thin_border
            if row_fill:
                cell.fill = row_fill
            
            if col_idx == 1:
                cell.alignment = Alignment(horizontal="center")
            elif col_idx == 5:
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = '#,##0.00'
                total_amount += amount
            else:
                cell.alignment = Alignment(horizontal="left")
                
        current_row += 1
        
    ws.append([])
    ws.append(["Total Spends", "", "", "", total_amount])
    total_row = current_row + 1
    
    ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=4)
    total_label_cell = ws.cell(row=total_row, column=1)
    total_label_cell.font = total_font
    total_label_cell.alignment = Alignment(horizontal="right")
    
    total_val_cell = ws.cell(row=total_row, column=5)
    total_val_cell.font = total_font
    total_val_cell.alignment = Alignment(horizontal="right")
    total_val_cell.number_format = '#,##0.00'
    total_val_cell.border = double_bottom_border
    
    for col in ws.columns:
        max_len = 0
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        for cell in col:
            val = str(cell.value or '')
            if cell.row == 2:
                continue
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = f'attachment; filename="expenzo_group_{group.name}_{datetime.now().strftime("%Y%m%d")}.xlsx"'
    wb.save(response)
    return response


# ──────────────────────────────────────────────────────────────
#  SCAN RECEIPT  –  OCR text parsing endpoint
#  Accepts raw text extracted by client-side Tesseract.js,
#  parses structured expense fields, returns JSON.
#  Does NOT modify any existing model or API.
# ──────────────────────────────────────────────────────────────
@login_required
def scan_receipt_api(request):
    """Parse OCR-extracted receipt text and return structured expense data."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    raw_text = strip_tags(body.get('text', ''))[:6000]
    ocr_confidence = float(body.get('ocr_confidence', 0))

    if not raw_text or len(raw_text.strip()) < 4:
        return JsonResponse({'error': 'No readable text found. Please upload a clearer image.'}, status=400)

    result = _parse_receipt_text(raw_text, ocr_confidence)
    return JsonResponse(result)


def _try_parse_date_str(s):
    """Try multiple date formats; return 'YYYY-MM-DD' string or None."""
    import re
    import dateparser
    
    s = s.strip()
    s = re.sub(r'^[:\s\-]+|[:\s\-]+$', '', s)
    if not s:
        return None
        
    try:
        parsed_dt = dateparser.parse(
            s,
            settings={
                "DATE_ORDER": "DMY",
                "PREFER_DAY_OF_MONTH": "first",
                "STRICT_PARSING": True
            }
        )
        if parsed_dt:
            y = parsed_dt.year
            mo = parsed_dt.month
            d = parsed_dt.day
            if 2000 <= y <= 2100:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    except Exception:
        pass
            
    return None


def _parse_receipt_text(text, ocr_confidence=0):
    """
    Rule-based receipt parser converting raw OCR text into structured expense fields.
    """
    import re

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    text_lower = text.lower()

    # ── 1. Merchant Extraction ─────────────────────────────────────
    # Check for explicit vendor/merchant labels first, then fall back
    merchant = None
    merchant_labels = [
        r'vendor\s+name', r'vendor', r'merchant\s+name', r'merchant',
        r'store\s+name', r'store', r'seller\s+name', r'seller',
        r'shop\s+name', r'shop'
    ]
    ignore_merchant_patterns = [
        r'\bwelcome\b', r'\bthank\b', r'\binvoice\b', r'\breceipt\b', r'\bbill\b',
        r'\btax\b', r'\bgst\b', r'\bvat\b', r'\bphone\b', r'\btel\b', r'\bmob\b',
        r'\bdate\b', r'\btime\b', r'\bcash\s+memo\b', r'\bduplicate\b', r'\boriginal\b',
        r'\btotal\b', r'\bamount\b', r'\bpayable\b', r'\bpaid\b', r'\bgrand\b', r'\bsubtotal\b',
        r'\bchange\b', r'\bcard\b', r'\bupi\b', r'\bcash\b', r'\bpayment\b'
    ]

    for label in merchant_labels:
        for line in lines:
            low_line = line.lower()
            m = re.search(r'\b' + label + r'\b[:\s\-]*', low_line)
            if m:
                val = line[m.end():].strip()
                if val and len(val) >= 2 and not any(re.search(pat, val.lower()) for pat in ignore_merchant_patterns):
                    merchant = val
                    break
        if merchant:
            break

    if not merchant:
        top_lines = lines[:8]
        for line in top_lines:
            line_clean = line.strip()
            if not line_clean:
                continue
            if not re.search(r'[a-zA-Z]', line_clean):
                continue
            if re.match(r'^[\W\d_]+$', line_clean):
                continue
            
            low_line = line_clean.lower()
            if any(re.search(pat, low_line) for pat in ignore_merchant_patterns):
                continue
                
            merchant = line_clean
            break

    # ── 2. Date Extraction ─────────────────────────────────────────
    # Recognize labels: Date, DATE, Invoice Date, Bill Date, Transaction Date, Txn Date
    # Support formats: dd/mm/yyyy, d/m/yyyy, yyyy-mm-dd, 05/05/2026, 5/5/2026, May 5 2026
    # Never guess dates. Never swap day and month unless format is explicitly known.
    # Leave empty if not found.
    date_val = None
    date_labels = [
        r'transaction\s+date', r'invoice\s+date', r'bill\s+date', r'txn\s+date', r'date'
    ]
    exclude_date_words = {
        'receipt no', 'receipt number', 'receipt#', 'bill no', 'bill number', 'bill#',
        'invoice no', 'invoice number', 'invoice#', 'time', 'volume', 'rate', 'amount',
        'mobile', 'vehicle', 'veh no', 'veh#'
    }
    
    # Try finding by labels first
    for label in date_labels:
        for line in lines:
            low_line = line.lower()
            if any(w in low_line for w in exclude_date_words):
                continue
                
            m = re.search(r'\b' + label + r'\b[:\s\-]*', low_line)
            if m:
                # Extract immediately following text
                after_text = line[m.end():].strip()
                
                # Check for standard date pattern matches inside after_text
                # ISO check
                m_iso = re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', after_text)
                if m_iso:
                    parsed = _try_parse_date_str(m_iso.group(0))
                    if parsed:
                        date_val = parsed
                        break
                        
                # Word month check
                m_word = re.search(r'\b(?:[a-z]{3,9}\s+\d{1,2}|\d{1,2}\s+[a-z]{3,9})[\s,]+\d{4}\b', after_text, re.IGNORECASE)
                if m_word:
                    parsed = _try_parse_date_str(m_word.group(0))
                    if parsed:
                        date_val = parsed
                        break
                        
                # Slashes/Dashes check
                m_num = re.search(r'\b\d{1,2}[-/.]\d{1,2}[-/.]\d{4}\b', after_text)
                if m_num:
                    # Clean trailing periods or separators
                    cleaned_num = m_num.group(0).replace('.', '-')
                    parsed = _try_parse_date_str(cleaned_num)
                    if parsed:
                        date_val = parsed
                        break
        if date_val:
            break

    # If no labeled date, search remaining text
    if not date_val:
        for line in lines:
            low_line = line.lower()
            if any(w in low_line for w in exclude_date_words):
                continue
                
            m_iso = re.search(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', line)
            if m_iso:
                parsed = _try_parse_date_str(m_iso.group(0))
                if parsed:
                    date_val = parsed
                    break
            
            m_word = re.search(r'\b(?:[a-z]{3,9}\s+\d{1,2}|\d{1,2}\s+[a-z]{3,9})[\s,]+\d{4}\b', line, re.IGNORECASE)
            if m_word:
                parsed = _try_parse_date_str(m_word.group(0))
                if parsed:
                    date_val = parsed
                    break
                    
            m_num = re.search(r'\b\d{1,2}[-/.]\d{1,2}[-/.]\d{4}\b', line)
            if m_num:
                cleaned_num = m_num.group(0).replace('.', '-')
                parsed = _try_parse_date_str(cleaned_num)
                if parsed:
                    date_val = parsed
                    break

    # ── 3. Amount Extraction ───────────────────────────────────────
    # Prioritize labels: Total, Grand Total, Amount, Amount(Rs.), Net Amount, Amount Payable
    # Ignore: Rate, Volume, Tax, Subtotal, Discount, MRP
    # If multiple exist, select the final payable amount.
    amount = None
    priorities = ['grand total', 'amount payable', 'net amount', 'amount(rs.)', 'amount', 'total']
    ignore_amt_words = {'rate', 'volume', 'tax', 'subtotal', 'discount', 'mrp', 'cgst', 'sgst', 'igst', 'gst', 'vat'}
    
    amount_candidates = []
    
    for line in lines:
        low_line = line.lower()
        if any(w in low_line for w in ignore_amt_words):
            continue
            
        for label in priorities:
            # Match the label exactly in text (with lax spacing/symbols)
            clean_line_no_spaces = re.sub(r'[^a-z0-9]', '', low_line)
            clean_label = re.sub(r'[^a-z0-9]', '', label)
            if clean_label in clean_line_no_spaces:
                nums = re.findall(r'([0-9,]+\.[0-9]{2}|[0-9,]+)', line)
                if nums:
                    try:
                        val = float(nums[-1].replace(',', ''))
                        if val > 0:
                            amount_candidates.append(val)
                            break
                    except ValueError:
                        pass
                        
    if amount_candidates:
        # Multiple amounts exist: Select the final payable amount (last match in the document)
        amount = amount_candidates[-1]
        
    # Generic fallback if no prioritized labels match
    if amount is None:
        for line in reversed(lines):
            low_line = line.lower()
            if any(w in low_line for w in ignore_amt_words):
                continue
            if 'total' in low_line or 'payable' in low_line or 'amount' in low_line:
                nums = re.findall(r'([0-9,]+\.[0-9]{2}|[0-9,]+)', line)
                if nums:
                    try:
                        val = float(nums[-1].replace(',', ''))
                        if val > 0:
                            amount = val
                            break
                    except ValueError:
                        pass

    # ── 4. Payment Method ──────────────────────────────────────────
    # Detect: Cash, UPI, Credit Card, Debit Card, Wallet, Net Banking
    payment_method = None
    pm_mapping = {
        'cash': 'Cash',
        'upi': 'UPI',
        'gpay': 'UPI',
        'phonepe': 'UPI',
        'paytm': 'UPI',
        'credit card': 'Credit Card',
        'visa': 'Credit Card',
        'mastercard': 'Credit Card',
        'debit card': 'Debit Card',
        'wallet': 'Wallet',
        'net banking': 'Net Banking',
        'netbanking': 'Net Banking',
        'bank transfer': 'Net Banking'
    }
    
    for kw, method in pm_mapping.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
            payment_method = method
            break

    # ── 5. Category Mapping ────────────────────────────────────────
    # Petrol, Fuel, Diesel, Uber, Ola, Metro → Transport (Travel)
    # Restaurant, Cafe, Food Court → Food
    # Medical Store, Pharmacy → Healthcare (Health)
    # Electricity, Gas Bill, Water Bill → Bills (Utilities)
    # Movie, Cinema, Netflix → Entertainment
    # Shopping Mall, Amazon, Flipkart → Shopping
    category_mapping = [
        ('Travel', ['petrol', 'fuel', 'diesel', 'uber', 'ola', 'metro']),
        ('Food', ['restaurant', 'cafe', 'food court']),
        ('Health', ['medical store', 'pharmacy']),
        ('Utilities', ['electricity', 'gas bill', 'water bill', 'newspaper', 'news']),
        ('Entertainment', ['movie', 'cinema', 'netflix']),
        ('Shopping', ['shopping mall', 'amazon', 'flipkart'])
    ]
    
    category = None
    for cat, keywords in category_mapping:
        if any(kw in text_lower for kw in keywords):
            category = cat
            break

    return {
        'merchant':       merchant or '',
        'amount':         amount,
        'tax':            None,
        'date':           date_val or '',
        'currency':       'INR',
        'category':       category or '',
        'payment_method': payment_method or '',
        'receipt_no':     '',
        'confidence':     100,
    }


@rate_limit(limit=60, window=60)
@login_required
def spending_streaks_view(request):
    user = request.user
    
    # Process recurring items dynamically
    process_recurring_finance(user)
    
    # Fetch all personal expenses
    expenses = PersonalExpense.objects.filter(user=user).order_by('-date')
    
    # Serialize expenses for streak calculations
    expense_history_data = [
        {
            'date': exp.date.strftime('%Y-%m-%d'),
            'amount': exp.amount,
            'category': exp.category,
            'description': exp.description
        }
        for exp in expenses
    ]
    expense_history_json = json.dumps(expense_history_data)
    
    context = {
        'expense_history_json': expense_history_json
    }
    return render(request, 'streaks.html', context)

