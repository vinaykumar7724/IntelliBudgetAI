# Budget Validation - Quick Reference Guide

## Installation

Add to `requirements.txt`:
```
python-dateutil
```

## Import in Your Code

```python
from utils.budget_validator import check_budget_status, get_all_budgets_status, get_warned_categories
```

## Basic Usage

### Get Status for One Category
```python
status = check_budget_status(user_id=1, category='Food')
print(status['status'])          # 'ok', 'warning', 'exceeded', 'fully_used', 'no_budget'
print(status['spent'])           # 800.0
print(status['limit'])           # 600.0 or None
print(status['message'])         # "⚠️ You have exceeded..."
```

### Get Status for All Categories
```python
all_statuses = get_all_budgets_status(user_id=1)
# {'Food': {...}, 'Transport': {...}, ...}

for category, status in all_statuses.items():
    if status['status'] == 'exceeded':
        print(f"Alert: {category} budget exceeded!")
```

### Get Only Warnings
```python
warnings = get_warned_categories(user_id=1)
# Returns list of status dicts where status in ['warning', 'exceeded', 'fully_used']

for warning in warnings:
    print(f"{warning['category']}: {warning['message']}")
```

## Status Values & Meanings

| Status | Meaning | Action |
|--------|---------|--------|
| `ok` | Spending < 80% of budget | ✓ All good |
| `warning` | 80% ≤ Spending < 100% | ⚠️ Getting close |
| `fully_used` | Spending = 100% | ✓ Budget fully used |
| `exceeded` | Spending > 100% | 🚨 Over budget |
| `no_budget` | No budget set | ℹ️ Just confirm |

## Integration Patterns

### Pattern 1: After Adding Expense (Chatbot/API)
```python
# Always save expense first
expense = Expense(user_id=user.id, amount=800, category='Food')
db.session.add(expense)
db.session.commit()

# Then check budget
status = check_budget_status(user.id, 'Food')

# Build response
if status['limit'] is None:
    response = f"✓ Added ₹{amount}. No budget set."
elif status['status'] == 'exceeded':
    response = f"🚨 {status['message']}"
elif status['status'] == 'warning':
    response = f"⚠️ {status['message']}"
else:
    response = f"✓ {status['message']}"
```

### Pattern 2: Dashboard Display
```python
@app.route('/dashboard')
def dashboard():
    # Show all budget statuses
    all_statuses = get_all_budgets_status(current_user.id)
    
    context = {
        'budgets': all_statuses,
        'warnings': get_warned_categories(current_user.id)
    }
    return render_template('dashboard.html', **context)
```

### Pattern 3: API Endpoint
```python
@app.route('/api/budget-status/<category>')
def api_status(category):
    status = check_budget_status(current_user.id, category)
    return jsonify(status)
```

## Response Dictionary Structure

```python
{
    'status': 'exceeded',              # str: status code
    'category': 'Food',                # str: expense category
    'spent': 800.0,                    # float: total spent this month
    'limit': 600.0,                    # float or None: budget limit
    'exceeded_by': 200.0,              # float or None: only if exceeded
    'percentage_used': 133,            # int: 0-100+
    'message': 'User-friendly text...' # str: display message
}
```

## Common Scenarios

### Scenario 1: User adds 800 to Food (budget 600)
```python
status = check_budget_status(user.id, 'Food')
# {
#     'status': 'exceeded',
#     'spent': 800.0,
#     'limit': 600.0,
#     'exceeded_by': 200.0,
#     'percentage_used': 133,
#     'message': '⚠️ You have exceeded your Food budget by ₹200...'
# }
```

### Scenario 2: User adds 100 to Transport (no budget set)
```python
status = check_budget_status(user.id, 'Transport')
# {
#     'status': 'no_budget',
#     'spent': 100.0,
#     'limit': None,
#     'exceeded_by': None,
#     'percentage_used': 0,
#     'message': '✅ Expense added under Transport. No budget limit set...'
# }
```

### Scenario 3: Check if any warnings exist
```python
warnings = get_warned_categories(user.id)
if warnings:
    # Show notification badge
    alert_count = len(warnings)
```

## Frontend Integration (JavaScript)

```javascript
// Fetch budget status after adding expense
async function addExpense(amount, category) {
    // Add expense via API
    let res = await fetch('/api/add-expense', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({amount, category})
    });
    
    let data = await res.json();
    let status = data.budget_status;
    
    // Display appropriate alert
    if (status.status === 'exceeded') {
        showAlert('danger', `🚨 ${status.message}`);
    } else if (status.status === 'warning') {
        showAlert('warning', `⚠️ ${status.message}`);
    } else if (status.status === 'fully_used') {
        showAlert('info', `✓ ${status.message}`);
    } else {
        showAlert('success', `✓ ${status.message}`);
    }
}

// Fetch all warnings for dashboard
async function loadBudgetWarnings() {
    let res = await fetch('/api/budget-warnings');
    let data = await res.json();
    
    if (data.warning_count > 0) {
        showWarningsPanel(data.warnings);
    }
}
```

## Debugging

### Check database contents
```python
from models import Budget, Expense
from sqlalchemy import func
from datetime import datetime

user_id = 1
category = 'Food'

# List all budgets
budgets = Budget.query.filter_by(user_id=user_id).all()
for b in budgets:
    print(f"{b.category}: ₹{b.limit_amount}")

# List all expenses this month
today = datetime.utcnow()
month_start = datetime(today.year, today.month, 1)
expenses = Expense.query.filter(
    Expense.user_id == user_id,
    Expense.date >= month_start
).all()
for e in expenses:
    print(f"{e.category}: ₹{e.amount} on {e.date}")

# Calculate total for category
total = db.session.query(func.sum(Expense.amount)).filter(
    Expense.user_id == user_id,
    Expense.category == category,
    Expense.date >= month_start
).scalar()
print(f"Total {category}: ₹{total or 0}")
```

## Error Handling

The system handles these automatically:
- ✓ No budget set → `limit = None`
- ✓ No expenses yet → `spent = 0.0`
- ✓ Database None → Converts to 0
- ✓ Floating point precision → Rounded to 2 decimals
- ✓ Division by zero → Returns percentage 0

No try-catch needed for normal usage!

## Testing

```bash
# Run tests
python test_budget_validator.py

# Expected output:
# Results: 7 passed, 0 failed
```

## Performance Notes

- **Query speed**: Single aggregation query per category (<10ms)
- **Caching**: Consider caching for dashboards if 1000s of budgets
- **Monthly filtering**: Automatic using date range

## Gotchas & Tips

1. **Always save expense first**, then check budget
2. **Category name matters**: Case-sensitive matching
3. **Current month only**: Uses `datetime.utcnow()`
4. **None handling**: `func.sum()` returns None if no rows
5. **Percentage**: Can exceed 100%, shows as integer

## Support & Questions

Check [BUDGET_VALIDATION_GUIDE.md](BUDGET_VALIDATION_GUIDE.md) for comprehensive docs
