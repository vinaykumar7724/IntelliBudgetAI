"""utils/nlp.py — NLP helpers for IntelliBudget AI chatbot."""
import re
from datetime import datetime, timedelta

# ── Try to import dateparser (Feature 4 dependency) ──────────────────────────
try:
    import dateparser
    _DATEPARSER_AVAILABLE = True
except ImportError:
    _DATEPARSER_AVAILABLE = False


# ── Category keyword map ──────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    'Food':       ['food', 'eat', 'lunch', 'dinner', 'breakfast', 'restaurant',
                   'grocery', 'groceries', 'snack', 'coffee', 'meal', 'swiggy',
                   'zomato', 'dominos', 'pizza', 'burger'],
    'Transport':  ['transport', 'bus', 'auto', 'cab', 'uber', 'ola', 'petrol',
                   'fuel', 'metro', 'train', 'flight', 'travel', 'taxi', 'bike'],
    'Shopping':   ['shopping', 'clothes', 'shirt', 'shoes', 'amazon', 'flipkart',
                   'myntra', 'dress', 'purchase', 'buy', 'bought'],
    'Health':     ['health', 'medicine', 'doctor', 'hospital', 'pharmacy',
                   'medical', 'clinic', 'tablet', 'drug', 'gym', 'fitness'],
    'Education':  ['education', 'book', 'course', 'school', 'college', 'fees',
                   'tuition', 'study', 'class', 'udemy', 'coursera'],
    'Bills':      ['bill', 'electricity', 'water', 'rent', 'internet', 'wifi',
                   'phone', 'recharge', 'broadband', 'gas', 'maintenance'],
    'Entertainment': ['entertainment', 'movie', 'netflix', 'prime', 'hotstar',
                      'spotify', 'game', 'concert', 'theatre', 'outing', 'fun'],
}

_WEEKDAYS = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2,
    'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6,
}


# ── Amount + category extraction ─────────────────────────────────────────────

def extract_amount_category(text: str, user_id: int = None):
    """
    Extract (amount, category) from a natural-language expense message.

    Returns
    -------
    tuple  (float | None, str)
        amount   – the numeric value found, or None
        category – matched category name, or 'Other'
    """
    text_lower = text.lower()

    # ── Amount extraction ────────────────────────────────────────────────────
    amount = None

    # Match patterns like: 500, 1,500, 1500.50, Rs.500, ₹500, INR 500
    amount_patterns = [
        r'(?:rs\.?|₹|inr\s*)(\d[\d,]*(?:\.\d{1,2})?)',  # currency prefix
        r'(\d[\d,]*(?:\.\d{1,2})?)\s*(?:rs\.?|₹|rupees?)',  # currency suffix
        r'\b(\d[\d,]*(?:\.\d{1,2})?)\b',                 # bare number
    ]

    for pattern in amount_patterns:
        match = re.search(pattern, text_lower)
        if match:
            raw = match.group(1).replace(',', '')
            try:
                amount = float(raw)
                break
            except ValueError:
                continue

    # ── Category extraction ──────────────────────────────────────────────────
    def _norm(s: str) -> str:
        return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()

    # 1) Try to capture an explicit category after common prepositions
    # Examples:
    # - "Add 200 to Food"
    # - "Spent 150 on groceries"
    # - "Paid 500 for rent"
    explicit = None
    m = re.search(r'\b(?:to|on|for|in)\s+([a-z][a-z0-9 &_-]{1,40})', text_lower)
    if m:
        explicit = m.group(1).strip()

    # 2) Build candidate categories (defaults + user-defined, if provided)
    candidates = set(CATEGORY_KEYWORDS.keys()) | {'Other', 'Bills', 'Food', 'Transport', 'Shopping', 'Health', 'Education'}
    if user_id is not None:
        try:
            from models import UserCategory
            user_cats = UserCategory.query.filter_by(user_id=user_id).all()
            for c in user_cats:
                if c and c.name:
                    candidates.add(c.name)
        except Exception:
            pass

    # Map normalized -> original for comparison
    norm_map = { _norm(c): c for c in candidates if _norm(c) }

    # 3) Exact/contains match against explicit phrase first
    if explicit:
        ne = _norm(explicit)
        if ne in norm_map:
            return amount, norm_map[ne]
        for k, orig in norm_map.items():
            if ne and (ne in k or k in ne):
                return amount, orig

    # 4) Keyword-based fallback (existing behavior)
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return amount, cat

    # 5) Final attempt: match any candidate category name appearing in the text
    nt = _norm(text)
    for k, orig in sorted(norm_map.items(), key=lambda x: len(x[0]), reverse=True):
        if k and f' {k} ' in f' {nt} ':
            return amount, orig

    category = 'Other'

    return amount, category


def extract_description(text: str) -> str:
    """Extract a short description from a message (first 100 chars, cleaned)."""
    # Remove common command words
    cleaned = re.sub(
        r'\b(add|added|spent|spend|paid|pay|record|log|save)\b',
        '', text, flags=re.IGNORECASE
    ).strip()
    return cleaned[:100] if cleaned else text[:100]


# ── Date extraction (Feature 4) ───────────────────────────────────────────────

def extract_date(text: str) -> datetime:
    """
    Extract a date from free-form text.

    Handles:
      - "today"
      - "yesterday", "day before yesterday"
      - "N days ago"
      - "last Monday / Tuesday / ..."
      - "this Monday / Tuesday / ..."
      - Full date strings via dateparser ("15th March", "10/03/2024", etc.)
      - Falls back to datetime.utcnow() if nothing is found

    Parameters
    ----------
    text : str  Raw message from the user

    Returns
    -------
    datetime  The detected date (time set to current UTC time of day)
    """
    today   = datetime.utcnow()
    text_lo = text.lower()

    # 1. "today"
    if re.search(r'\btoday\b', text_lo):
        return today

    # 2. "day before yesterday"
    if re.search(r'\bday before yesterday\b', text_lo):
        return today - timedelta(days=2)

    # 3. "yesterday"
    if re.search(r'\byesterday\b', text_lo):
        return today - timedelta(days=1)

    # 4. "N days ago"
    m = re.search(r'(\d+)\s+days?\s+ago', text_lo)
    if m:
        return today - timedelta(days=int(m.group(1)))

    # 5. "last <weekday>"
    m = re.search(
        r'last\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
        text_lo
    )
    if m:
        target = _WEEKDAYS[m.group(1)]
        delta  = (today.weekday() - target) % 7 or 7
        return today - timedelta(days=delta)

    # 6. "this <weekday>"
    m = re.search(
        r'this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
        text_lo
    )
    if m:
        target = _WEEKDAYS[m.group(1)]
        delta  = (today.weekday() - target) % 7
        return today - timedelta(days=delta)

    # 7. Delegate to dateparser for structured dates ("15th March", "10/03")
    if _DATEPARSER_AVAILABLE:
        parsed = dateparser.parse(
            text,
            settings={
                'PREFER_DATES_FROM':        'past',
                'RETURN_AS_TIMEZONE_AWARE': False,
                'RELATIVE_BASE':            today,
            }
        )
        if parsed:
            return parsed

    # 8. Fallback — today
    return today
