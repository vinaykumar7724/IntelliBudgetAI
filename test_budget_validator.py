"""
Unit tests for budget validation system.

Usage:
    python -m pytest test_budget_validator.py -v
    or
    python test_budget_validator.py  (if pytest not available)
"""

import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import db, User, Expense, Budget
from utils.budget_validator import check_budget_status, get_all_budgets_status, get_warned_categories, check_category_budget


def setup_test_db():
    """Setup in-memory SQLite database for testing."""
    from app import app
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    
    with app.app_context():
        db.create_all()
        return app


def test_no_budget():
    """Test: No budget set for category."""
    app = setup_test_db()
    
    with app.app_context():
        # Create user
        user = User(username="test_user", email="test@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        
        # Add expense WITHOUT budget
        expense = Expense(user_id=user.id, amount=100, category="Food")
        db.session.add(expense)
        db.session.commit()
        
        # Check status
        status = check_budget_status(user.id, "Food")
        
        assert status['status'] == 'no_budget', f"Expected 'no_budget', got {status['status']}"
        assert status['spent'] == 100.0
        assert status['limit'] is None
        assert status['percentage_used'] == 0
        print("✓ Test PASSED: No budget scenario")


def test_within_budget():
    """Test: Expense within budget limit."""
    app = setup_test_db()
    
    with app.app_context():
        # Create user
        user = User(username="test_user2", email="test2@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        
        # Set budget
        budget = Budget(user_id=user.id, category="Food", limit_amount=600)
        db.session.add(budget)
        db.session.commit()
        
        # Add expense within limit
        expense = Expense(user_id=user.id, amount=400, category="Food")
        db.session.add(expense)
        db.session.commit()
        
        # Check status
        status = check_budget_status(user.id, "Food")
        
        assert status['status'] == 'ok', f"Expected 'ok', got {status['status']}"
        assert status['spent'] == 400.0
        assert status['limit'] == 600.0
        assert status['percentage_used'] == 67
        print("✓ Test PASSED: Within budget scenario")


def test_budget_warning():
    """Test: Budget usage at 80%+."""
    app = setup_test_db()
    
    with app.app_context():
        # Create user
        user = User(username="test_user3", email="test3@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        
        # Set budget
        budget = Budget(user_id=user.id, category="Food", limit_amount=600)
        db.session.add(budget)
        db.session.commit()
        
        # Add expense at 80%
        expense = Expense(user_id=user.id, amount=480, category="Food")
        db.session.add(expense)
        db.session.commit()
        
        # Check status
        status = check_budget_status(user.id, "Food")
        
        assert status['status'] == 'warning', f"Expected 'warning', got {status['status']}"
        assert status['spent'] == 480.0
        assert status['limit'] == 600.0
        assert status['percentage_used'] == 80
        assert '80%' in status['message'].lower() or '⚠️' in status['message']
        print("✓ Test PASSED: Budget warning scenario (80%)")


def test_budget_exceeded():
    """Test: Expense exceeds budget."""
    app = setup_test_db()
    
    with app.app_context():
        # Create user
        user = User(username="test_user4", email="test4@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        
        # Set budget
        budget = Budget(user_id=user.id, category="Food", limit_amount=600)
        db.session.add(budget)
        db.session.commit()
        
        # Add expense exceeding limit
        expense = Expense(user_id=user.id, amount=800, category="Food")
        db.session.add(expense)
        db.session.commit()
        
        # Check status
        status = check_budget_status(user.id, "Food")
        
        assert status['status'] == 'exceeded', f"Expected 'exceeded', got {status['status']}"
        assert status['spent'] == 800.0
        assert status['limit'] == 600.0
        assert status['exceeded_by'] == 200.0
        assert status['percentage_used'] == 133
        print("✓ Test PASSED: Budget exceeded scenario")


def test_budget_fully_used():
    """Test: Budget fully used (100%)."""
    app = setup_test_db()
    
    with app.app_context():
        # Create user
        user = User(username="test_user5", email="test5@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        
        # Set budget
        budget = Budget(user_id=user.id, category="Food", limit_amount=600)
        db.session.add(budget)
        db.session.commit()
        
        # Add expense exactly at limit
        expense = Expense(user_id=user.id, amount=600, category="Food")
        db.session.add(expense)
        db.session.commit()
        
        # Check status
        status = check_budget_status(user.id, "Food")
        
        assert status['status'] == 'fully_used', f"Expected 'fully_used', got {status['status']}"
        assert status['spent'] == 600.0
        assert status['limit'] == 600.0
        assert status['percentage_used'] == 100
        print("✓ Test PASSED: Budget fully used scenario")


def test_multiple_expenses_same_month():
    """Test: Multiple expenses in same month are aggregated."""
    app = setup_test_db()
    
    with app.app_context():
        # Create user
        user = User(username="test_user6", email="test6@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        
        # Set budget
        budget = Budget(user_id=user.id, category="Food", limit_amount=600)
        db.session.add(budget)
        db.session.commit()
        
        # Add multiple expenses
        expense1 = Expense(user_id=user.id, amount=200, category="Food")
        expense2 = Expense(user_id=user.id, amount=250, category="Food")
        expense3 = Expense(user_id=user.id, amount=100, category="Food")
        db.session.add_all([expense1, expense2, expense3])
        db.session.commit()
        
        # Check status
        status = check_budget_status(user.id, "Food")
        
        assert status['spent'] == 550.0, f"Expected 550.0, got {status['spent']}"
        assert status['status'] == 'ok'
        assert status['percentage_used'] == 92
        print("✓ Test PASSED: Multiple expenses aggregation")


def test_multiple_categories():
    """Test: Multiple categories with different statuses."""
    app = setup_test_db()
    
    with app.app_context():
        # Create user
        user = User(username="test_user7", email="test7@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        
        # Set multiple budgets
        budget1 = Budget(user_id=user.id, category="Food", limit_amount=600)
        budget2 = Budget(user_id=user.id, category="Transport", limit_amount=500)
        db.session.add_all([budget1, budget2])
        db.session.commit()
        
        # Add expenses
        exp1 = Expense(user_id=user.id, amount=800, category="Food")  # Exceeded
        exp2 = Expense(user_id=user.id, amount=200, category="Transport")  # OK
        db.session.add_all([exp1, exp2])
        db.session.commit()
        
        # Check all budgets
        all_status = get_all_budgets_status(user.id)
        
        assert len(all_status) == 2
        assert all_status['Food']['status'] == 'exceeded'
        assert all_status['Transport']['status'] == 'ok'
        
        # Check warnings
        warnings = get_warned_categories(user.id)
        assert len(warnings) == 1
        assert warnings[0]['category'] == 'Food'
        print("✓ Test PASSED: Multiple categories with different statuses")


def test_check_category_budget():
    """Test explicit category budget checking logic."""
    app = setup_test_db()
    
    with app.app_context():
        user = User(username="test_cat", email="cat@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        
        # no budget -> status no_budget
        eps = Expense(user_id=user.id, amount=100, category="Food")
        db.session.add(eps)
        db.session.commit()
        status = check_category_budget(user.id, "Food")
        assert status['status'] == 'no_budget'
        
        # set budget and test within
        b = Budget(user_id=user.id, category="Food", limit_amount=500)
        db.session.add(b)
        db.session.commit()
        status = check_category_budget(user.id, "Food")
        assert status['status'] == 'within'
        assert status['difference'] == 400.0
        
        # add more expense to exceed
        e2 = Expense(user_id=user.id, amount=200, category="Food")
        db.session.add(e2)
        db.session.commit()
        status = check_category_budget(user.id, "Food")
        assert status['status'] == 'exceeded'
        assert status['difference'] == 100.0
        print("✓ Test PASSED: check_category_budget function")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("Budget Validator Tests")
    print("="*60 + "\n")
    
    tests = [
        test_no_budget,
        test_within_budget,
        test_budget_warning,
        test_budget_exceeded,
        test_budget_fully_used,
        test_multiple_expenses_same_month,
        test_multiple_categories,
        test_check_category_budget,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ Test FAILED: {test_func.__name__}")
            print(f"  Error: {e}\n")
            failed += 1
        except Exception as e:
            print(f"✗ Test ERROR: {test_func.__name__}")
            print(f"  Error: {e}\n")
            failed += 1
    
    print("="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
