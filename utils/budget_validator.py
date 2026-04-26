"""utils/budget_validator.py — Budget validation logic for IntelliBudget AI."""
from datetime import datetime
from sqlalchemy import func
from dateutil.relativedelta import relativedelta


def check_budget_status(user_id: int, category: str) -> dict:
    """
    Check the budget status for a given user and category for the current month.

    Parameters
    ----------
    user_id  : int   The user's database ID
    category : str   The expense category name (case-sensitive)

    Returns
    -------
    dict with keys:
        status          – 'ok' | 'warning' | 'exceeded' | 'fully_used' | 'no_budget'
        category        – str
        spent           – float  (total spent this month)
        limit           – float | None
        exceeded_by     – float | None
        percentage_used – int
        message         – str   (user-friendly message with emoji)
    """
    # Import here to avoid circular imports at module level
    from models import db, Expense, Budget

    category = (category or '').strip()

    today      = datetime.utcnow()
    month_start = datetime(today.year, today.month, 1)
    month_end   = month_start + relativedelta(months=1)

    # Total spent this month for this category
    raw_total = db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id,
        func.lower(func.trim(Expense.category)) == func.lower(category),
        Expense.date >= month_start,
        Expense.date < month_end,
    ).scalar()

    spent = round(float(raw_total or 0), 2)

    # Budget limit
    budget = Budget.query.filter(
        Budget.user_id == user_id,
        func.lower(func.trim(Budget.category)) == func.lower(category),
    ).first()

    if budget is None:
        return {
            'status':          'no_budget',
            'category':        category,
            'spent':           spent,
            'limit':           None,
            'exceeded_by':     None,
            'percentage_used': 0,
            'message': (
                f'✅ Expense added under {category}. '
                f'No budget limit set. (Spent: ₹{spent:,.2f})'
            ),
        }

    limit      = round(float(budget.limit_amount), 2)
    pct        = int((spent / limit * 100)) if limit > 0 else 0
    exceeded_by = round(spent - limit, 2) if spent > limit else None

    if spent > limit:
        status  = 'exceeded'
        message = (
            f'🚨 You have exceeded your {category} budget by ₹{exceeded_by:,.2f}. '
            f'(Spent: ₹{spent:,.2f} / Limit: ₹{limit:,.2f})'
        )
    elif spent == limit:
        status  = 'fully_used'
        message = (
            f'✅ You have fully used your {category} budget. '
            f'(Spent: ₹{spent:,.2f} / Limit: ₹{limit:,.2f})'
        )
    elif pct >= 80:
        status  = 'warning'
        message = (
            f'⚠️ You have used {pct}% of your {category} budget. '
            f'(Spent: ₹{spent:,.2f} / Limit: ₹{limit:,.2f})'
        )
    else:
        status  = 'ok'
        message = (
            f'✅ You are within your {category} budget. '
            f'(Spent: ₹{spent:,.2f} / Limit: ₹{limit:,.2f})'
        )

    return {
        'status':          status,
        'category':        category,
        'spent':           spent,
        'limit':           limit,
        'exceeded_by':     exceeded_by,
        'percentage_used': pct,
        'message':         message,
    }


def get_all_budgets_status(user_id: int) -> dict:
    """
    Return budget status for every category that has a budget set.

    Returns
    -------
    dict  { category_name: status_dict, ... }
    """
    from models import Budget
    budgets = Budget.query.filter_by(user_id=user_id).all()
    return {b.category: check_budget_status(user_id, b.category) for b in budgets}


def get_warned_categories(user_id: int) -> list:
    """
    Return only the categories whose status is warning, exceeded, or fully_used.

    Returns
    -------
    list of status dicts
    """
    all_statuses = get_all_budgets_status(user_id)
    alert_states = {'warning', 'exceeded', 'fully_used'}
    return [s for s in all_statuses.values() if s['status'] in alert_states]


def check_category_budget(user_id: int, category: str) -> dict:
    """
    Simplified check: returns 'within', 'exceeded', or 'no_budget'
    plus the difference amount.

    Kept for backward-compatibility with existing tests.
    """
    from models import db, Expense, Budget

    category = (category or '').strip()

    today       = datetime.utcnow()
    month_start = datetime(today.year, today.month, 1)
    month_end   = month_start + relativedelta(months=1)

    raw_total = db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id,
        func.lower(func.trim(Expense.category)) == func.lower(category),
        Expense.date >= month_start,
        Expense.date < month_end,
    ).scalar()
    spent  = round(float(raw_total or 0), 2)
    budget = Budget.query.filter(
        Budget.user_id == user_id,
        func.lower(func.trim(Budget.category)) == func.lower(category),
    ).first()

    if budget is None:
        return {'status': 'no_budget', 'spent': spent, 'limit': None, 'difference': 0.0}

    limit = round(float(budget.limit_amount), 2)
    diff  = round(abs(spent - limit), 2)

    return {
        'status':     'exceeded' if spent > limit else 'within',
        'spent':      spent,
        'limit':      limit,
        'difference': diff,
    }
