"""
utils/evaluate_model.py
========================
Evaluate the trained LSTM chatbot model and cache results as JSON.

Run standalone:
    python -m utils.evaluate_model

Import in Flask:
    from utils.evaluate_model import run_evaluation, load_metrics
"""
import json
import os
import pickle
import numpy as np
from datetime import datetime
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, classification_report, confusion_matrix,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS_PATH   = os.path.join(_BASE, 'models', 'metrics.json')
MODEL_PATH     = os.path.join(_BASE, 'models', 'model.h5')
TOKENIZER_PATH = os.path.join(_BASE, 'models', 'tokenizer.pkl')
ENCODER_PATH   = os.path.join(_BASE, 'models', 'label_encoder.pkl')
MAX_LEN        = 20

# ── Training corpus (keep in sync with train_model.py) ───────────────────────
TRAINING_DATA = [
    ('I spent 100 on food',                 'add_expense'),
    ('Paid 500 for transport',              'add_expense'),
    ('Add 2000 shopping expense',           'add_expense'),
    ('I bought groceries for 300',          'add_expense'),
    ('Spent 150 on medicine',               'add_expense'),
    ('Add 50 to entertainment',             'add_expense'),
    ('Record 800 electricity bill',         'add_expense'),
    ('Show my expenses',                    'show_expense'),
    ('What did I spend last month',         'show_expense'),
    ('List all my transactions',            'show_expense'),
    ('How much did I spend this month?',    'show_analysis'),
    ('Give me a spending summary',          'show_analysis'),
    ('Analyse my finances',                 'show_analysis'),
    ('Set salary to 5000',                  'set_salary'),
    ('My monthly income is 8000',           'set_salary'),
    ('Update my salary to 60000',           'set_salary'),
    ('Hello',                               'greeting'),
    ('Hi there',                            'greeting'),
    ('Hey chatbot',                         'greeting'),
    ('Are my expenses okay?',               'warning_query'),
    ('Am I over budget?',                   'warning_query'),
    ('Show budget warnings',                'warning_query'),
]


def run_evaluation(save: bool = True) -> dict:
    """
    Load the trained model, run predictions, and compute performance metrics.

    Parameters
    ----------
    save : bool   If True, write metrics.json to models/ directory

    Returns
    -------
    dict  Full metrics dictionary
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f'Model not found at {MODEL_PATH}. '
            'Run: python train_model.py'
        )

    from tensorflow.keras.models import load_model
    from tensorflow.keras.preprocessing.sequence import pad_sequences

    model = load_model(MODEL_PATH)

    with open(TOKENIZER_PATH, 'rb') as f:
        tokenizer = pickle.load(f)
    with open(ENCODER_PATH, 'rb') as f:
        encoder = pickle.load(f)

    texts  = [t for t, _ in TRAINING_DATA]
    labels = [lbl for _, lbl in TRAINING_DATA]

    seqs   = tokenizer.texts_to_sequences(texts)
    padded = pad_sequences(seqs, maxlen=MAX_LEN, padding='post')
    y_true = encoder.transform(labels)

    probs  = model.predict(padded, verbose=0)
    y_pred = np.argmax(probs, axis=1)

    class_names = list(encoder.classes_)

    report_dict = classification_report(
        y_true, y_pred,
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )
    cm = confusion_matrix(y_true, y_pred).tolist()

    metrics = {
        'evaluated_at': datetime.utcnow().isoformat(),
        'num_samples':  len(texts),
        'classes':      class_names,
        'overall': {
            'accuracy':        round(float(accuracy_score(y_true, y_pred)), 4),
            'macro_precision': round(float(precision_score(
                                   y_true, y_pred,
                                   average='macro', zero_division=0)), 4),
            'macro_recall':    round(float(recall_score(
                                   y_true, y_pred,
                                   average='macro', zero_division=0)), 4),
            'macro_f1':        round(float(f1_score(
                                   y_true, y_pred,
                                   average='macro', zero_division=0)), 4),
            'weighted_f1':     round(float(f1_score(
                                   y_true, y_pred,
                                   average='weighted', zero_division=0)), 4),
        },
        'per_class': {
            cls: {
                'precision': round(float(report_dict[cls]['precision']), 4),
                'recall':    round(float(report_dict[cls]['recall']),    4),
                'f1':        round(float(report_dict[cls]['f1-score']),  4),
                'support':   int(report_dict[cls]['support']),
            }
            for cls in class_names
            if cls in report_dict
        },
        'confusion_matrix': cm,
    }

    if save:
        os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
        with open(METRICS_PATH, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f'[evaluate_model] Saved → {METRICS_PATH}')

    return metrics


def load_metrics() -> dict:
    """Load cached metrics JSON.  Returns None if not yet generated."""
    if not os.path.exists(METRICS_PATH):
        return None
    with open(METRICS_PATH, 'r') as f:
        return json.load(f)


# ── CLI entry-point ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('Running model evaluation...\n')
    m = run_evaluation(save=True)
    o = m['overall']

    print(f"{'Metric':<25} {'Value':>10}")
    print('-' * 37)
    print(f"{'Accuracy':<25} {o['accuracy']*100:>9.2f}%")
    print(f"{'Macro Precision':<25} {o['macro_precision']*100:>9.2f}%")
    print(f"{'Macro Recall':<25} {o['macro_recall']*100:>9.2f}%")
    print(f"{'Macro F1':<25} {o['macro_f1']*100:>9.2f}%")
    print(f"{'Weighted F1':<25} {o['weighted_f1']*100:>9.2f}%")

    print('\nPer-class F1 scores:')
    for cls, vals in m['per_class'].items():
        bar = '█' * int(vals['f1'] * 20)
        print(f'  {cls:<20} {bar:<20} {vals["f1"]:.4f}')
