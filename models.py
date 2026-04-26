from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(150), unique=True, nullable=False)
    email          = db.Column(db.String(150), unique=True, nullable=False)
    password_hash  = db.Column(db.String(256), nullable=False)
    monthly_salary = db.Column(db.Float, default=0.0)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    expenses   = db.relationship('Expense',      backref='owner', lazy=True)
    budgets    = db.relationship('Budget',       backref='owner', lazy=True)
    categories = db.relationship('UserCategory', backref='owner', lazy=True,
                                 cascade='all, delete-orphan')

    def set_password(self, password):
        # Werkzeug 3 defaults to scrypt, but some Python builds (incl. certain
        # macOS toolchain Pythons) ship without hashlib.scrypt enabled.
        # Use PBKDF2 which is widely supported and still secure for this app.
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Expense(db.Model):
    __tablename__ = 'expenses'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    category    = db.Column(db.String(100))
    description = db.Column(db.String(255))
    date        = db.Column(db.DateTime, default=datetime.utcnow)


class Budget(db.Model):
    __tablename__ = 'budgets'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category     = db.Column(db.String(100), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)


class UserCategory(db.Model):
    """User-defined custom expense categories."""
    __tablename__ = 'user_categories'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    icon       = db.Column(db.String(50),  default='🏷️')
    color      = db.Column(db.String(7),   default='#6366f1')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_user_category'),
    )

    def to_dict(self):
        return {
            'id':    self.id,
            'name':  self.name,
            'icon':  self.icon,
            'color': self.color,
        }
