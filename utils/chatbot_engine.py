"""utils/chatbot_engine.py — Intent-based chatbot engine for IntelliBudget AI."""
import html
import os
import pickle
import numpy as np
from datetime import datetime

from models import db, Expense, Budget
from utils.nlp import extract_amount_category, extract_description, extract_date
from utils.budget_validator import check_budget_status

# ── Lazy model loading ────────────────────────────────────────────────────────
_model        = None
_tokenizer    = None
_label_encoder = None
MAX_LEN       = 20

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models')


def _load_model():
    """Load LSTM model and artefacts once, then cache."""
    global _model, _tokenizer, _label_encoder
    if _model is not None:
        return

    try:
        from tensorflow.keras.models import load_model as keras_load
        _model = keras_load(os.path.join(MODEL_DIR, 'model.h5'))

        with open(os.path.join(MODEL_DIR, 'tokenizer.pkl'), 'rb') as f:
            _tokenizer = pickle.load(f)

        with open(os.path.join(MODEL_DIR, 'label_encoder.pkl'), 'rb') as f:
            _label_encoder = pickle.load(f)

    except Exception as e:
        print(f'[Chatbot] Warning: could not load model — {e}')
        _model = None


def _predict_intent(text: str) -> str:
    """Return the predicted intent label for the given text."""
    _load_model()

    if _model is None:
        return _fallback_intent(text)

    try:
        from tensorflow.keras.preprocessing.sequence import pad_sequences
        seq    = _tokenizer.texts_to_sequences([text])
        padded = pad_sequences(seq, maxlen=MAX_LEN, padding='post')
        probs  = _model.predict(padded, verbose=0)
        idx    = int(np.argmax(probs, axis=1)[0])
        return _label_encoder.inverse_transform([idx])[0]
    except Exception:
        return _fallback_intent(text)


def _fallback_intent(text: str) -> str:
    """Rule-based intent detection when model is unavailable."""
    text_lo = text.lower()

    add_keywords     = ['add', 'spent', 'spend', 'paid', 'pay', 'bought',
                        'expense', 'record', 'log']
    show_keywords    = ['show', 'list', 'view', 'display', 'history', 'transactions']
    analysis_kw      = ['analysis', 'analyse', 'analyze', 'report',
                        'how much', 'total']
    budget_summary_kw = ['budget summary', 'budget status']
    near_limits_kw    = ['near budget', 'near limit', 'near limits', 'close to budget', 'close to limit']
    salary_kw        = ['salary', 'income', 'earning', 'set salary', 'update salary']
    warning_kw       = ['warning', 'over budget', 'budget', 'exceeded', 'alert']
    greeting_kw      = ['hello', 'hi', 'hey', 'good morning', 'good evening']
    help_kw          = ['help', 'what can you do', 'commands', 'options']

    if any(k in text_lo for k in greeting_kw):
        return 'greeting'
    if any(k in text_lo for k in help_kw):
        return 'help'
    if any(k in text_lo for k in salary_kw):
        return 'set_salary'
    if any(k in text_lo for k in budget_summary_kw):
        return 'budget_summary'
    if any(k in text_lo for k in near_limits_kw):
        return 'near_limits'
    if any(k in text_lo for k in warning_kw):
        return 'warning_query'
    if any(k in text_lo for k in analysis_kw):
        return 'show_analysis'
    if any(k in text_lo for k in show_keywords):
        return 'show_expense'
    if any(k in text_lo for k in add_keywords):
        return 'add_expense'

    import re
    if re.search(r'\b\d+\b', text_lo):
        return 'add_expense'

    return 'unknown'


# ── Intent handlers ───────────────────────────────────────────────────────────

def _handle_greeting(message: str, user) -> str:
    text_lo = (message or '').strip().lower()

    # If the user greets with "hi/hello/hey", mirror that.
    if 'hi' in text_lo.split():
        greeting = 'Hi'
    elif 'hello' in text_lo.split():
        greeting = 'Hello'
    elif 'hey' in text_lo.split():
        greeting = 'Hey'
    elif 'good morning' in text_lo:
        greeting = 'Good morning'
    elif 'good afternoon' in text_lo:
        greeting = 'Good afternoon'
    elif 'good evening' in text_lo:
        greeting = 'Good evening'
    else:
        # Otherwise use local time (UTC was causing wrong greetings).
        hour = datetime.now().hour
        if hour < 12:
            greeting = 'Good morning'
        elif hour < 17:
            greeting = 'Good afternoon'
        else:
            greeting = 'Good evening'
    return (
        f'{greeting}, {user.username}! 👋\n'
        'I can help you:\n'
        '• Add expenses — "Add 500 to Food"\n'
        '• View expenses — "Show my expenses"\n'
        '• Check budget  — "Am I over budget?"\n'
        '• Set salary    — "Set salary to 50000"'
    )


def _handle_help(message: str, user) -> str:
    return (
        '❓ Help — what you can do\n\n'
        '✅ Add an expense:\n'
        '  • "Add 250 to Food"\n'
        '  • "Spent 120 on bills yesterday"\n\n'
        '📋 Recent expenses:\n'
        '  • "Show my expenses"\n\n'
        '📊 Summaries:\n'
        '  • "This month summary"\n'
        '  • "Show summary"\n\n'
        '📈 Budgets:\n'
        '  • "Budget summary" (all categories)\n'
        '  • "Near limits" (risky categories)\n'
        '  • "Am I over budget?" (alerts only)\n\n'
        '💰 Salary:\n'
        '  • "Set salary to 50000"\n\n'
        'Tip: use the Quick buttons under the chat.'
    )


def _handle_add_expense(message: str, user) -> str:
    amount, category = extract_amount_category(message, user_id=user.id)
    description      = extract_description(message)

    if amount is None:
        return (
            '❓ I could not find an amount in your message.\n'
            'Try: "Add 500 to Food" or "Spent 200 on transport"'
        )

    # Feature 4: detect date from message
    expense_date = extract_date(message)
    date_str     = expense_date.strftime('%d %b %Y')

    expense = Expense(
        user_id     = user.id,
        amount      = amount,
        category    = category,
        description = description,
        date        = expense_date,
    )
    db.session.add(expense)
    db.session.commit()

    # Budget validation
    budget_status = check_budget_status(user.id, category)

    resp  = f'✅ Added ₹{amount:.2f} to {category} on {date_str}.\n'
    resp += budget_status['message']
    return resp


def _handle_show_expense(message: str, user) -> str:
    today    = datetime.utcnow()
    m_start  = datetime(today.year, today.month, 1)
    expenses = Expense.query.filter(
        Expense.user_id == user.id,
        Expense.date    >= m_start,
    ).order_by(Expense.date.desc()).limit(10).all()

    if not expenses:
        return '📭 No expenses recorded this month yet.'

    lines = ['📋 Your recent expenses this month:\n']
    for e in expenses:
        lines.append(
            f'  • {e.date.strftime("%d %b")} | {e.category} | ₹{e.amount:.2f}'
            + (f' — {e.description}' if e.description else '')
        )
    total = sum(e.amount for e in Expense.query.filter(
        Expense.user_id == user.id,
        Expense.date    >= m_start,
    ).all())
    lines.append(f'\nMonth total so far: ₹{total:.2f}')
    return '\n'.join(lines)


def _handle_show_analysis(message: str, user) -> str:
    today   = datetime.utcnow()
    m_start = datetime(today.year, today.month, 1)
    expenses = Expense.query.filter(
        Expense.user_id == user.id,
        Expense.date    >= m_start,
    ).all()

    if not expenses:
        return '📊 No expenses found for analysis this month.'

    total     = sum(e.amount for e in expenses)
    breakdown = {}
    for e in expenses:
        breakdown[e.category] = breakdown.get(e.category, 0) + e.amount

    salary    = user.monthly_salary or 0
    remaining = salary - total

    # Build budget lookup (case/whitespace-insensitive)
    budgets = Budget.query.filter(Budget.user_id == user.id).all()
    budget_by_norm = {(b.category or '').strip().lower(): float(b.limit_amount) for b in budgets}

    def _status_ui(status: str) -> tuple[str, str, str]:
        if status == 'exceeded':
            return (
                '<span class="budget-sum-status budget-sum-status--bad">'
                '<span class="budget-sum-dot" aria-hidden="true"></span> Over</span>',
                'bad',
                'bad',
            )
        if status in ('warning', 'fully_used'):
            label = 'Near limit' if status == 'warning' else 'At limit'
            return (
                f'<span class="budget-sum-status budget-sum-status--warn">'
                f'<span class="budget-sum-dot" aria-hidden="true"></span> {label}</span>',
                'warn',
                'warn',
            )
        if status == 'no_budget':
            return (
                '<span class="budget-sum-status budget-sum-status--muted">'
                '<span class="budget-sum-dot" aria-hidden="true"></span> No limit</span>',
                'muted',
                'muted',
            )
        return (
            '<span class="budget-sum-status budget-sum-status--ok">'
            '<span class="budget-sum-dot" aria-hidden="true"></span> OK</span>',
            'ok',
            'ok',
        )

    rows = []
    for cat, amt in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
        cat_str = str(cat or 'Other')
        cat_esc = html.escape(cat_str)
        spent = float(amt or 0)
        limit = budget_by_norm.get(cat_str.strip().lower())

        if limit is None or limit <= 0:
            status = 'no_budget'
            pct = 0
        else:
            pct = int((spent / limit) * 100) if limit else 0
            if spent > limit:
                status = 'exceeded'
            elif spent == limit:
                status = 'fully_used'
            elif pct >= 80:
                status = 'warning'
            else:
                status = 'ok'

        status_html, bar_mod, pct_mod = _status_ui(status)
        bar_width = min(max(pct, 0), 100)

        limit_html = 'Not set' if limit is None or limit <= 0 else f'₹{float(limit):,.2f}'
        pct_html = '--' if limit is None or limit <= 0 else f'{pct}%'

        rows.append(
            '<div class="budget-sum-row">'
            '<div class="budget-sum-row__top">'
            f'<span class="budget-sum-row__name">{cat_esc}</span>'
            f'{status_html}'
            '</div>'
            '<div class="budget-sum-track" role="progressbar" '
            f'aria-valuenow="{bar_width}" aria-valuemin="0" aria-valuemax="100">'
            f'<div class="budget-sum-fill budget-sum-fill--{bar_mod}" '
            f'style="width:{bar_width}%"></div>'
            '</div>'
            '<div class="budget-sum-row__bottom">'
            '<div class="budget-sum-spent">'
            '<span class="budget-sum-label">Spent</span>'
            f'<strong>₹{spent:,.2f}</strong>'
            '</div>'
            '<div class="budget-sum-limit">'
            '<span class="budget-sum-label">Limit</span>'
            f'<span>{limit_html}</span>'
            '</div>'
            f'<div class="budget-sum-pct budget-sum-pct--{pct_mod}">'
            f'<strong>{pct_html}</strong>'
            '</div>'
            '</div>'
            '</div>'
        )

    salary_bits = []
    salary_bits.append(f'<div class="budget-sum-metric"><span>Total spent</span><strong>₹{total:,.2f}</strong></div>')
    if salary:
        salary_bits.append(f'<div class="budget-sum-metric"><span>Monthly salary</span><strong>₹{salary:,.2f}</strong></div>')
        salary_bits.append(f'<div class="budget-sum-metric"><span>Remaining</span><strong>₹{remaining:,.2f}</strong></div>')

    return (
        '<div class="chat-rich-wrapper chat-summary-wrapper">'
        '<div class="budget-sum-card">'
        '<div class="budget-sum-card__head">'
        f'<div class="budget-sum-card__title">📊 Summary — {today.strftime("%B %Y")}</div>'
        '<p class="budget-sum-card__sub">Progress vs your category limits</p>'
        f'<div class="budget-sum-metrics">{"".join(salary_bits)}</div>'
        '</div>'
        f'<div class="budget-sum-list">{"".join(rows)}</div>'
        '</div>'
        '</div>'
    )


def _handle_total_summary(message: str, user) -> str:
    """All-time summary across all transactions for the user."""
    expenses = Expense.query.filter(Expense.user_id == user.id).all()
    if not expenses:
        return '📦 No expenses recorded yet.'

    total = sum(e.amount for e in expenses)
    count = len(expenses)

    breakdown = {}
    for e in expenses:
        cat = e.category or 'Other'
        breakdown[cat] = breakdown.get(cat, 0) + e.amount

    top = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:5]

    budgets = Budget.query.filter(Budget.user_id == user.id).all()
    budget_by_norm = {(b.category or '').strip().lower(): float(b.limit_amount) for b in budgets}

    rows = []
    for cat, amt in top:
        cat_str = str(cat or 'Other')
        cat_esc = html.escape(cat_str)
        spent = float(amt or 0)
        limit = budget_by_norm.get(cat_str.strip().lower())

        # All-time vs monthly limit is still useful for context; cap visual bar at 100.
        if limit is None or limit <= 0:
            status = 'no_budget'
            pct = 0
        else:
            pct = int((spent / limit) * 100) if limit else 0
            status = 'exceeded' if spent > limit else ('fully_used' if spent == limit else ('warning' if pct >= 80 else 'ok'))

        # Reuse same UI mapping as budget summary handler (duplicated lightly for clarity)
        if status == 'exceeded':
            status_html, bar_mod, pct_mod = (
                '<span class="budget-sum-status budget-sum-status--bad"><span class="budget-sum-dot" aria-hidden="true"></span> Over</span>',
                'bad',
                'bad',
            )
        elif status in ('warning', 'fully_used'):
            label = 'Near limit' if status == 'warning' else 'At limit'
            status_html, bar_mod, pct_mod = (
                f'<span class="budget-sum-status budget-sum-status--warn"><span class="budget-sum-dot" aria-hidden="true"></span> {label}</span>',
                'warn',
                'warn',
            )
        elif status == 'no_budget':
            status_html, bar_mod, pct_mod = (
                '<span class="budget-sum-status budget-sum-status--muted"><span class="budget-sum-dot" aria-hidden="true"></span> No limit</span>',
                'muted',
                'muted',
            )
        else:
            status_html, bar_mod, pct_mod = (
                '<span class="budget-sum-status budget-sum-status--ok"><span class="budget-sum-dot" aria-hidden="true"></span> OK</span>',
                'ok',
                'ok',
            )

        bar_width = min(max(pct, 0), 100)
        limit_html = 'Not set' if limit is None or limit <= 0 else f'₹{float(limit):,.2f}'
        pct_html = '--' if limit is None or limit <= 0 else f'{pct}%'

        rows.append(
            '<div class="budget-sum-row">'
            '<div class="budget-sum-row__top">'
            f'<span class="budget-sum-row__name">{cat_esc}</span>'
            f'{status_html}'
            '</div>'
            '<div class="budget-sum-track" role="progressbar" '
            f'aria-valuenow="{bar_width}" aria-valuemin="0" aria-valuemax="100">'
            f'<div class="budget-sum-fill budget-sum-fill--{bar_mod}" style="width:{bar_width}%"></div>'
            '</div>'
            '<div class="budget-sum-row__bottom">'
            '<div class="budget-sum-spent">'
            '<span class="budget-sum-label">Spent</span>'
            f'<strong>₹{spent:,.2f}</strong>'
            '</div>'
            '<div class="budget-sum-limit">'
            '<span class="budget-sum-label">Limit</span>'
            f'<span>{limit_html}</span>'
            '</div>'
            f'<div class="budget-sum-pct budget-sum-pct--{pct_mod}"><strong>{pct_html}</strong></div>'
            '</div>'
            '</div>'
        )

    return (
        '<div class="chat-rich-wrapper chat-total-summary-wrapper">'
        '<div class="budget-sum-card">'
        '<div class="budget-sum-card__head">'
        '<div class="budget-sum-card__title">🧾 Summary (All time)</div>'
        f'<p class="budget-sum-card__sub">{count} transactions · Total spent ₹{total:,.2f}</p>'
        '</div>'
        f'<div class="budget-sum-list">{"".join(rows)}</div>'
        '</div>'
        '</div>'
    )

def _handle_set_salary(message: str, user) -> str:
    import re
    match = re.search(r'(\d[\d,]*(?:\.\d{1,2})?)', message)
    if not match:
        return '❓ Please include the salary amount, e.g. "Set salary to 50000"'

    amount = float(match.group(1).replace(',', ''))
    user.monthly_salary = amount
    db.session.commit()
    return f'✅ Monthly salary updated to ₹{amount:,.2f}.'


def _handle_warning_query(message: str, user) -> str:
    from utils.budget_validator import get_warned_categories
    warnings = get_warned_categories(user.id)

    if not warnings:
        return '✅ All your budgets are within safe limits!'

    lines = [f'⚠️ Budget alerts ({len(warnings)} categories):\n']
    for w in warnings:
        lines.append(f'  • {w["message"]}')
    return '\n'.join(lines)


def _handle_budget_summary(message: str, user) -> str:
    """
    HTML card layout: every category with a budget limit, progress bar, spent/limit/%.
    """
    from utils.budget_validator import get_all_budgets_status

    all_statuses = list(get_all_budgets_status(user.id).values())
    if not all_statuses:
        return (
            '📊 No budgets set yet.\n'
            'Go to Profile → Budget Limits to add category limits.'
        )

    # Stable, scannable order (matches typical “list all budgets” expectations)
    all_statuses.sort(key=lambda s: (s.get('category') or '').lower())

    def _status_ui(status: str, pct: int):
        """Returns (status_html, bar_modifier, pct_modifier)."""
        if status == 'exceeded':
            return (
                '<span class="budget-sum-status budget-sum-status--bad">'
                '<span class="budget-sum-dot" aria-hidden="true"></span> Over</span>',
                'bad',
                'bad',
            )
        if status == 'warning':
            return (
                '<span class="budget-sum-status budget-sum-status--warn">'
                '<span class="budget-sum-dot" aria-hidden="true"></span> Near limit</span>',
                'warn',
                'warn',
            )
        if status == 'fully_used':
            return (
                '<span class="budget-sum-status budget-sum-status--warn">'
                '<span class="budget-sum-dot" aria-hidden="true"></span> At limit</span>',
                'warn',
                'warn',
            )
        return (
            '<span class="budget-sum-status budget-sum-status--ok">'
            '<span class="budget-sum-dot" aria-hidden="true"></span> OK</span>',
            'ok',
            'ok',
        )

    rows = []
    for s in all_statuses:
        cat = s.get('category') or '—'
        cat_esc = html.escape(str(cat))
        spent = float(s.get('spent') or 0)
        limit = s.get('limit')
        pct = int(s.get('percentage_used') or 0)
        status = s.get('status', 'ok')

        if limit is None:
            rows.append(
                '<div class="budget-sum-row budget-sum-row--plain">'
                f'<div class="budget-sum-row__name">{cat_esc}</div>'
                f'<div class="text-muted small">Spent {spent:,.2f} (no limit set)</div>'
                '</div>'
            )
            continue

        lim = float(limit)
        status_html, bar_mod, pct_mod = _status_ui(status, pct)
        bar_width = min(max(pct, 0), 100)

        rows.append(
            '<div class="budget-sum-row">'
            '<div class="budget-sum-row__top">'
            f'<span class="budget-sum-row__name">{cat_esc}</span>'
            f'{status_html}'
            '</div>'
            '<div class="budget-sum-track" role="progressbar" '
            f'aria-valuenow="{bar_width}" aria-valuemin="0" aria-valuemax="100">'
            f'<div class="budget-sum-fill budget-sum-fill--{bar_mod}" '
            f'style="width:{bar_width}%"></div>'
            '</div>'
            '<div class="budget-sum-row__bottom">'
            '<div class="budget-sum-spent">'
            '<span class="budget-sum-label">Spent</span>'
            f'<strong>₹{spent:,.2f}</strong>'
            '</div>'
            '<div class="budget-sum-limit">'
            '<span class="budget-sum-label">Limit</span> '
            f'<span>₹{lim:,.2f}</span>'
            '</div>'
            f'<div class="budget-sum-pct budget-sum-pct--{pct_mod}">'
            f'<strong>{pct}%</strong>'
            '</div>'
            '</div>'
            '</div>'
        )

    body = '\n'.join(rows)
    return (
        '<div class="chat-rich-wrapper chat-budget-summary-wrapper">'
        '<div class="budget-sum-card">'
        '<div class="budget-sum-card__head">'
        '<div class="budget-sum-card__title">📊 Budget Summary</div>'
        '<p class="budget-sum-card__sub">All categories with their budget limits</p>'
        '</div>'
        f'<div class="budget-sum-list">{body}</div>'
        '</div>'
        '</div>'
    )


def _handle_near_limits(message: str, user) -> str:
    """
    HTML card layout: only the most at-risk categories (closest to / over the limit).
    """
    from utils.budget_validator import get_all_budgets_status

    all_statuses = list(get_all_budgets_status(user.id).values())
    # Only categories where a limit exists make sense for "near limits"
    all_statuses = [s for s in all_statuses if s.get('limit') is not None]

    if not all_statuses:
        return (
            '📈 No budget limits set yet.\n'
            'Go to Profile → Budget Limits to add category limits.'
        )

    def _risk_key(s: dict):
        status = s.get('status') or 'ok'
        # Higher = riskier
        status_weight = {
            'exceeded': 4,
            'fully_used': 3,
            'warning': 2,
            'ok': 1,
        }.get(status, 0)
        pct = float(s.get('percentage_used') or 0)
        spent = float(s.get('spent') or 0)
        return (status_weight, pct, spent)

    all_statuses.sort(key=_risk_key, reverse=True)
    top = all_statuses[:6]

    # Reuse the same row rendering used by budget summary by delegating into the same structure:
    # (Copy a minimal status->UI mapping here for clarity)
    def _status_ui(status: str):
        if status == 'exceeded':
            return (
                '<span class="budget-sum-status budget-sum-status--bad"><span class="budget-sum-dot" aria-hidden="true"></span> Over</span>',
                'bad',
                'bad',
            )
        if status == 'warning':
            return (
                '<span class="budget-sum-status budget-sum-status--warn"><span class="budget-sum-dot" aria-hidden="true"></span> Near limit</span>',
                'warn',
                'warn',
            )
        if status == 'fully_used':
            return (
                '<span class="budget-sum-status budget-sum-status--warn"><span class="budget-sum-dot" aria-hidden="true"></span> At limit</span>',
                'warn',
                'warn',
            )
        return (
            '<span class="budget-sum-status budget-sum-status--ok"><span class="budget-sum-dot" aria-hidden="true"></span> OK</span>',
            'ok',
            'ok',
        )

    rows = []
    for s in top:
        cat = s.get('category') or '—'
        cat_esc = html.escape(str(cat))
        spent = float(s.get('spent') or 0)
        limit = float(s.get('limit') or 0)
        pct = int(s.get('percentage_used') or 0)
        status = s.get('status', 'ok')

        status_html, bar_mod, pct_mod = _status_ui(status)
        bar_width = min(max(pct, 0), 100)

        rows.append(
            '<div class="budget-sum-row">'
            '<div class="budget-sum-row__top">'
            f'<span class="budget-sum-row__name">{cat_esc}</span>'
            f'{status_html}'
            '</div>'
            '<div class="budget-sum-track" role="progressbar" '
            f'aria-valuenow="{bar_width}" aria-valuemin="0" aria-valuemax="100">'
            f'<div class="budget-sum-fill budget-sum-fill--{bar_mod}" style="width:{bar_width}%"></div>'
            '</div>'
            '<div class="budget-sum-row__bottom">'
            '<div class="budget-sum-spent">'
            '<span class="budget-sum-label">Spent</span>'
            f'<strong>₹{spent:,.2f}</strong>'
            '</div>'
            '<div class="budget-sum-limit">'
            '<span class="budget-sum-label">Limit</span>'
            f'<span>₹{limit:,.2f}</span>'
            '</div>'
            f'<div class="budget-sum-pct budget-sum-pct--{pct_mod}"><strong>{pct}%</strong></div>'
            '</div>'
            '</div>'
        )

    return (
        '<div class="chat-rich-wrapper chat-near-limits-wrapper">'
        '<div class="budget-sum-card">'
        '<div class="budget-sum-card__head">'
        '<div class="budget-sum-card__title">📈 Near Limits</div>'
        '<p class="budget-sum-card__sub">Categories closest to hitting (or exceeding) their limits</p>'
        '</div>'
        f'<div class="budget-sum-list">{"".join(rows)}</div>'
        '</div>'
        '</div>'
    )


def _handle_unknown(message: str, user) -> str:
    return (
        "🤔 I didn't quite understand that.\n"
        'You can say things like:\n'
        '  • "Add 300 to Food"\n'
        '  • "Show my expenses"\n'
        '  • "How much did I spend this month?"\n'
        '  • "Am I over budget?"\n'
        '  • "Set salary to 40000"'
    )


# ── Main dispatcher ───────────────────────────────────────────────────────────

_HANDLERS = {
    'greeting':      _handle_greeting,
    'help':          _handle_help,
    'add_expense':   _handle_add_expense,
    'show_expense':  _handle_show_expense,
    'show_analysis': _handle_show_analysis,
    'total_summary': _handle_total_summary,
    'set_salary':    _handle_set_salary,
    'warning_query': _handle_warning_query,
    'budget_summary': _handle_budget_summary,
    'near_limits': _handle_near_limits,
}


class Chatbot:
    """Main chatbot interface used by Flask routes."""

    def handle_message(self, message: str, user) -> str:
        if not message or not message.strip():
            return '💬 Please type a message.'

        msg = message.strip()

        # Command-based routing for quick actions so results are deterministic
        # and not dependent on the ML intent model.
        cmd = msg.lower()
        command_map = {
            '/recent': 'show_expense',
            '/near-limits': 'near_limits',
            '/budget-summary': 'budget_summary',
            '/alerts': 'warning_query',
            '/summary': 'show_analysis',
            '/summary-all': 'total_summary',
            '/total': 'total_summary',  # backward-compatible alias
            '/help': 'help',
        }
        if cmd in command_map:
            intent = command_map[cmd]
        else:
            # Prefer deterministic rule-based routing for common phrases
            # (prevents ML misclassification from repeating the wrong response).
            intent = _fallback_intent(msg)
            if intent == 'unknown':
                intent = _predict_intent(msg)
        handler = _HANDLERS.get(intent, _handle_unknown)
        return handler(msg, user)
