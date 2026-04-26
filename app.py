import os
from datetime import datetime
from flask_cors import CORS
from flask import Flask, render_template, url_for, flash, redirect, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from sqlalchemy.exc import IntegrityError
from config import Config
from utils.chatbot_engine import Chatbot
from utils.nlp import extract_amount_category
from utils.budget_validator import check_budget_status, get_all_budgets_status, get_warned_categories
from utils.pdf_report import generate_expense_report
from utils.evaluate_model import load_metrics, run_evaluation
import pandas as pd
from models import db, User, Expense, Budget, UserCategory

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.config.from_object(Config)

print('ENV DATABASE_URL =', os.environ.get('DATABASE_URL'))
print('CONFIG URI =', app.config.get('SQLALCHEMY_DATABASE_URI'))

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@app.before_request
def mobile_auth_middleware():
    user_id = request.headers.get('X-User-Id')
    if user_id and not current_user.is_authenticated:
        try:
            user = User.query.get(int(user_id))
            if user:
                login_user(user)
        except (ValueError, TypeError):
            pass


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

chatbot = Chatbot()

# ── Default categories (always available to every user) ───────────────────────
DEFAULT_CATEGORIES = [
    {'name': 'Food',       'icon': '🍔', 'color': '#f97316'},
    {'name': 'Transport',  'icon': '🚗', 'color': '#3b82f6'},
    {'name': 'Shopping',   'icon': '🛍️', 'color': '#ec4899'},
    {'name': 'Health',     'icon': '💊', 'color': '#10b981'},
    {'name': 'Education',  'icon': '📚', 'color': '#8b5cf6'},
    {'name': 'Bills',      'icon': '🏠', 'color': '#f59e0b'},
    {'name': 'Other',      'icon': '📦', 'color': '#6b7280'},
]


def get_all_categories(user_id):
    """Return merged list of default + user-defined categories."""
    user_cats  = UserCategory.query.filter_by(user_id=user_id).all()
    user_names = {c.name for c in user_cats}
    merged     = [d for d in DEFAULT_CATEGORIES if d['name'] not in user_names]
    merged    += [c.to_dict() for c in user_cats]
    return merged


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email    = (request.form.get('email') or '').strip()
        password = request.form.get('password')

        if not username or not email or not password:
            flash('Please fill all fields', 'danger')
            return redirect(url_for('signup'))

        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return redirect(url_for('signup'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('signup'))

        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return redirect(url_for('signup'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Username or email already exists', 'danger')
            return redirect(url_for('signup'))

        flash('Account created; please log in', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')
        user     = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    today         = datetime.utcnow()
    from_date_str = request.args.get('from_date')
    to_date_str   = request.args.get('to_date')

    # Support both custom date range AND legacy month/year selectors
    if from_date_str and to_date_str:
        try:
            start       = datetime.strptime(from_date_str, '%Y-%m-%d')
            end         = datetime.strptime(to_date_str,   '%Y-%m-%d').replace(
                              hour=23, minute=59, second=59)
            filter_mode = 'range'
        except ValueError:
            start       = datetime(today.year, today.month, 1)
            end         = today
            filter_mode = 'month'
    else:
        month = request.args.get('month')
        year  = request.args.get('year')
        try:
            m = int(month) if month else today.month
            y = int(year)  if year  else today.year
        except (ValueError, TypeError):
            m, y = today.month, today.year

        start = datetime(y, m, 1)
        end   = datetime(y, m + 1, 1) if m < 12 else datetime(y + 1, 1, 1)
        filter_mode = 'month'

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date    >= start,
        Expense.date    <= end,
    ).order_by(Expense.date.desc()).all()

    total     = sum(e.amount for e in expenses)
    remaining = (current_user.monthly_salary or 0) - total

    breakdown = {}
    for e in expenses:
        breakdown[e.category] = breakdown.get(e.category, 0) + e.amount

    over_budget = [
        b.category for b in current_user.budgets
        if breakdown.get(b.category, 0) > b.limit_amount
    ]

    return render_template('dashboard.html',
        total         = total,
        remaining     = remaining,
        breakdown     = breakdown,
        over_budget   = over_budget,
        selected_month= start,
        filter_mode   = filter_mode,
        expenses      = expenses,
        from_date     = start.strftime('%Y-%m-%d'),
        to_date       = (end if filter_mode == 'range' else today).strftime('%Y-%m-%d'),
    )


# ── Expenses: edit/delete (Dashboard) ─────────────────────────────────────────

@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense(expense_id):
    exp = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(exp)
        db.session.commit()
        flash('Expense deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Could not delete expense: {e}', 'danger')

    # Preserve dashboard filter (range view) if present
    from_date = request.form.get('from_date')
    to_date = request.form.get('to_date')
    if from_date and to_date:
        return redirect(url_for('dashboard', from_date=from_date, to_date=to_date))
    return redirect(url_for('dashboard'))


@app.route('/expenses/<int:expense_id>/update', methods=['POST'])
@login_required
def update_expense(expense_id):
    exp = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()

    amount = request.form.get('amount')
    category = (request.form.get('category') or '').strip()
    description = (request.form.get('description') or '').strip()
    date_str = request.form.get('date')

    try:
        amt = float(amount)
        if amt <= 0:
            flash('Amount must be positive', 'danger')
            return redirect(url_for('dashboard'))
        exp.amount = amt
        exp.category = category or exp.category
        exp.description = description
        if date_str:
            exp.date = datetime.strptime(date_str, '%Y-%m-%d')
        db.session.commit()
        flash('Expense updated', 'success')
    except ValueError:
        db.session.rollback()
        flash('Invalid amount/date', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Could not update expense: {e}', 'danger')

    from_date = request.form.get('from_date')
    to_date = request.form.get('to_date')
    if from_date and to_date:
        return redirect(url_for('dashboard', from_date=from_date, to_date=to_date))
    return redirect(url_for('dashboard'))


# ── Chatbot ───────────────────────────────────────────────────────────────────

@app.route('/chatbot', methods=['GET', 'POST'])
@login_required
def chatbot_view():
    if request.method == 'POST':
        message  = request.form.get('message')
        response = chatbot.handle_message(message, current_user)
        # Rich HTML responses must not get literal newlines turned into <br>
        if 'chat-rich-wrapper' not in response:
            response = response.replace('\n', '<br>')
        return jsonify({'response': response})
    return render_template('chatbot.html')


# ── Budgets ───────────────────────────────────────────────────────────────────

@app.route('/budgets', methods=['GET', 'POST'])
@login_required
def budgets():
    if request.method == 'POST':
        category     = (request.form.get('category') or '').strip()
        limit_amount = request.form.get('limit_amount')
        try:
            amt = float(limit_amount)
            b   = Budget(user_id=current_user.id, category=category, limit_amount=amt)
            db.session.add(b)
            db.session.commit()
            flash('Budget added', 'success')
        except ValueError:
            flash('Invalid amount', 'danger')

    return redirect(url_for('profile'))


@app.route('/budgets/<int:budget_id>/update', methods=['POST'])
@login_required
def update_budget(budget_id):
    """Update an existing budget limit."""
    limit_amount = request.form.get('limit_amount')
    b = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first_or_404()
    try:
        amt = float(limit_amount)
        if amt <= 0:
            flash('Budget limit must be positive', 'danger')
            return redirect(url_for('profile'))
        b.limit_amount = amt
        db.session.commit()
        flash('Budget updated', 'success')
    except (ValueError, TypeError):
        flash('Invalid amount', 'danger')
    return redirect(url_for('profile'))


@app.route('/budgets/<int:budget_id>/delete', methods=['POST'])
@login_required
def delete_budget(budget_id):
    b = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(b)
        db.session.commit()
        flash('Budget deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Could not delete budget: {e}', 'danger')
    return redirect(url_for('profile'))


# ── Profile ───────────────────────────────────────────────────────────────────

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        if 'monthly_salary' in request.form:
            salary = request.form.get('monthly_salary')
            try:
                current_user.monthly_salary = float(salary)
                db.session.commit()
                flash('Profile updated', 'success')
            except ValueError:
                flash('Invalid salary amount', 'danger')

        elif 'category' in request.form:
            category     = (request.form.get('category') or '').strip()
            limit_amount = request.form.get('limit_amount')
            try:
                amt = float(limit_amount)
                b   = Budget(user_id=current_user.id, category=category, limit_amount=amt)
                db.session.add(b)
                db.session.commit()
                flash('Budget added', 'success')
            except ValueError:
                flash('Invalid amount', 'danger')

    user_budgets = Budget.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', budgets=user_budgets)


# ── CSV Export ────────────────────────────────────────────────────────────────

@app.route('/export')
@login_required
def export_csv():
    import tempfile
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    df = pd.DataFrame([
        {
            'amount':      e.amount,
            'category':    e.category,
            'description': e.description,
            'date':        e.date.strftime('%Y-%m-%d'),
        }
        for e in expenses
    ])
    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = tmp.name
    return send_file(tmp_path, as_attachment=True)


# ── PDF Export (Feature 3) ────────────────────────────────────────────────────

@app.route('/export/pdf')
@login_required
def export_pdf():
    today         = datetime.utcnow()
    from_date_str = request.args.get('from_date')
    to_date_str   = request.args.get('to_date')

    try:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d') \
                    if from_date_str else datetime(today.year, today.month, 1)
        to_date   = datetime.strptime(to_date_str, '%Y-%m-%d').replace(
                        hour=23, minute=59, second=59) \
                    if to_date_str else today
    except ValueError:
        from_date = datetime(today.year, today.month, 1)
        to_date   = today

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date    >= from_date,
        Expense.date    <= to_date,
    ).order_by(Expense.date.desc()).all()

    buf      = generate_expense_report(
        user      = current_user,
        expenses  = expenses,
        from_date = from_date,
        to_date   = to_date,
        salary    = current_user.monthly_salary or 0,
    )
    filename = f'expenses_{from_date.strftime("%Y%m%d")}_{to_date.strftime("%Y%m%d")}.pdf'
    return send_file(buf, mimetype='application/pdf',
                     as_attachment=True, download_name=filename)



# ── Budget Validation API ─────────────────────────────────────────────────────

@app.route('/api/add-expense', methods=['POST'])
@login_required
def api_add_expense():
    try:
        data        = request.get_json()
        amount      = data.get('amount')
        category    = data.get('category', 'Other')
        description = data.get('description', '')

        if not amount:
            return jsonify({'success': False, 'error': 'Amount is required'}), 400

        try:
            amount = float(amount)
            if amount <= 0:
                return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid amount format'}), 400

        expense = Expense(
            user_id     = current_user.id,
            amount      = amount,
            category    = category,
            description = description,
        )
        db.session.add(expense)
        db.session.commit()

        budget_status = check_budget_status(current_user.id, category)

        return jsonify({
            'success':       True,
            'expense_id':    expense.id,
            'message':       f'Expense of ₹{amount} added to {category}',
            'budget_status': budget_status,
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/budget-status/<category>', methods=['GET'])
@login_required
def api_budget_status(category):
    try:
        return jsonify(check_budget_status(current_user.id, category)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/budget-warnings', methods=['GET'])
@login_required
def api_budget_warnings():
    try:
        warnings = get_warned_categories(current_user.id)
        return jsonify({'warnings': warnings, 'warning_count': len(warnings)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/all-budgets-status', methods=['GET'])
@login_required
def api_all_budgets_status():
    try:
        all_statuses = get_all_budgets_status(current_user.id)
        return jsonify({'budgets': all_statuses, 'total_categories': len(all_statuses)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Date Range Filter API (Feature 2) ─────────────────────────────────────────

@app.route('/api/expenses/filter', methods=['GET'])
@login_required
def api_filter_expenses():
    """Filter expenses by date range and optional category."""
    from_date_str = request.args.get('from_date')
    to_date_str   = request.args.get('to_date')
    category      = request.args.get('category')

    if not from_date_str or not to_date_str:
        return jsonify({'error': 'from_date and to_date are required'}), 400

    try:
        start = datetime.strptime(from_date_str, '%Y-%m-%d')
        end   = datetime.strptime(to_date_str,   '%Y-%m-%d').replace(
                    hour=23, minute=59, second=59)
    except ValueError:
        return jsonify({'error': 'Use YYYY-MM-DD format'}), 400

    q = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date    >= start,
        Expense.date    <= end,
    )
    if category:
        q = q.filter(Expense.category == category)

    expenses  = q.order_by(Expense.date.desc()).all()
    total     = sum(e.amount for e in expenses)
    breakdown = {}
    for e in expenses:
        breakdown[e.category] = breakdown.get(e.category, 0) + e.amount

    return jsonify({
        'expenses': [{
            'id':          e.id,
            'amount':      e.amount,
            'category':    e.category,
            'description': e.description,
            'date':        e.date.strftime('%Y-%m-%d'),
        } for e in expenses],
        'total':     total,
        'count':     len(expenses),
        'breakdown': breakdown,
    }), 200


# ── Custom Categories API (Feature 1) ─────────────────────────────────────────

@app.route('/api/categories', methods=['GET'])
@login_required
def api_get_categories():
    return jsonify({'categories': get_all_categories(current_user.id)}), 200


@app.route('/api/categories', methods=['POST'])
@login_required
def api_create_category():
    data  = request.get_json()
    name  = (data.get('name') or '').strip()
    icon  = data.get('icon',  '🏷️')
    color = data.get('color', '#6366f1')

    if not name:
        return jsonify({'success': False, 'error': 'Category name is required'}), 400
    if len(name) > 100:
        return jsonify({'success': False, 'error': 'Name too long (max 100 chars)'}), 400

    if UserCategory.query.filter_by(user_id=current_user.id, name=name).first():
        return jsonify({'success': False, 'error': f'"{name}" already exists'}), 409

    cat = UserCategory(user_id=current_user.id, name=name, icon=icon, color=color)
    db.session.add(cat)
    db.session.commit()
    return jsonify({'success': True, 'category': cat.to_dict()}), 201


@app.route('/api/categories/<int:cat_id>', methods=['DELETE'])
@login_required
def api_delete_category(cat_id):
    cat = UserCategory.query.filter_by(
        id=cat_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'success': True, 'message': f'"{cat.name}" deleted'}), 200

# MOBILE APP API ROUTES ─────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    data     = request.get_json()
    email    = data.get('email', '').strip()
    password = data.get('password', '')
    user     = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        login_user(user)
        return jsonify({
            'success':  True,
            'user_id':  user.id,
            'username': user.username,
            'email':    user.email,
            'salary':   user.monthly_salary or 0,
        }), 200
    return jsonify({'success': False, 'error': 'Invalid email or password'}), 401


@app.route('/api/auth/signup', methods=['POST'])
def api_auth_signup():
    data     = request.get_json()
    username = (data.get('username', '') or '').strip()
    email    = (data.get('email', '') or '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'success': False, 'error': 'All fields required'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'error': 'Password min 6 characters'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email already registered'}), 409
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'error': 'Username already taken'}), 409

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Username or email already exists'}), 409
    return jsonify({'success': True, 'message': 'Account created'}), 201


@app.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    today   = datetime.utcnow()
    m_start = datetime(today.year, today.month, 1)
    m_end   = datetime(today.year, today.month + 1, 1) \
              if today.month < 12 else datetime(today.year + 1, 1, 1)

    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date    >= m_start,
        Expense.date    <  m_end,
    ).order_by(Expense.date.desc()).all()

    total     = sum(e.amount for e in expenses)
    remaining = (current_user.monthly_salary or 0) - total

    breakdown = {}
    for e in expenses:
        breakdown[e.category] = breakdown.get(e.category, 0) + e.amount

    return jsonify({
        'total':     total,
        'remaining': remaining,
        'breakdown': breakdown,
        'expenses':  [{
            'id':          e.id,
            'amount':      e.amount,
            'category':    e.category,
            'description': e.description or '',
            'date':        e.date.strftime('%d %b %Y'),
        } for e in expenses],
    }), 200


@app.route('/api/chatbot', methods=['POST'])
@login_required
def api_chatbot():
    data    = request.get_json()
    message = data.get('message', '')
    if not message:
        return jsonify({'response': 'Please send a message'}), 400
    response = chatbot.handle_message(message, current_user)
    return jsonify({'response': response}), 200


@app.route('/api/salary/update', methods=['POST'])
@login_required
def api_update_salary():
    data   = request.get_json()
    salary = data.get('salary', 0)
    try:
        current_user.monthly_salary = float(salary)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/budgets/add', methods=['POST'])
@login_required
def api_add_budget():
    data     = request.get_json()
    category = data.get('category', '').strip()
    limit    = data.get('limit_amount', 0)
    if not category or not limit:
        return jsonify({'success': False, 'error': 'Category and limit required'}), 400
    try:
        b = Budget(
            user_id      = current_user.id,
            category     = category,
            limit_amount = float(limit),
        )
        db.session.add(b)
        db.session.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/budgets', methods=['GET'])
@login_required
def api_get_budgets():
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        'budgets': [{
            'id':           b.id,
            'category':     b.category,
            'limit_amount': b.limit_amount,
        } for b in budgets]
    }), 200


@app.route('/api/budgets/<int:budget_id>', methods=['PATCH', 'PUT'])
@login_required
def api_update_budget(budget_id):
    data = request.get_json() or {}
    limit = data.get('limit_amount')
    b = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first()
    if not b:
        return jsonify({'success': False, 'error': 'Budget not found'}), 404
    try:
        amt = float(limit)
        if amt <= 0:
            return jsonify({'success': False, 'error': 'Limit must be positive'}), 400
        b.limit_amount = amt
        db.session.commit()
        return jsonify({'success': True, 'budget': {
            'id': b.id, 'category': b.category, 'limit_amount': b.limit_amount
        }}), 200
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid limit_amount'}), 400


@app.route('/api/budgets/<int:budget_id>', methods=['DELETE'])
@login_required
def api_delete_budget(budget_id):
    b = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first()
    if not b:
        return jsonify({'success': False, 'error': 'Budget not found'}), 404
    try:
        db.session.delete(b)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)