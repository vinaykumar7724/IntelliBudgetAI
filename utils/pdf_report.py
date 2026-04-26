"""utils/pdf_report.py — PDF expense report generator for IntelliBudget AI."""
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie

# ── Page dimensions ───────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4          # 595 x 842 points
L_MARGIN = R_MARGIN = 2 * cm
USABLE_W = PAGE_W - L_MARGIN - R_MARGIN   # ~453 pt

# ── Brand palette ─────────────────────────────────────────────────────────────
BRAND_BLUE  = colors.HexColor('#2563eb')
BRAND_DARK  = colors.HexColor('#0f172a')
BRAND_LIGHT = colors.HexColor('#f1f5f9')
BRAND_GRAY  = colors.HexColor('#64748b')
ROW_ALT     = colors.HexColor('#f8fafc')

CATEGORY_COLORS = [
    '#3b82f6', '#f97316', '#10b981', '#ec4899',
    '#8b5cf6', '#f59e0b', '#06b6d4', '#84cc16',
    '#ef4444', '#6366f1',
]

# Use Rs. everywhere — avoids missing-glyph boxes on Windows Helvetica
CURRENCY = 'Rs.'


def _styles():
    return {
        'title': ParagraphStyle('IBtitle',
            fontName='Helvetica-Bold', fontSize=20,
            textColor=BRAND_BLUE,
            leading=24,
            spaceAfter=10),
        'subtitle': ParagraphStyle('IBsubtitle',
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=BRAND_GRAY,
            spaceAfter=4),
        'heading': ParagraphStyle('IBheading',
            fontName='Helvetica-Bold', fontSize=12,
            textColor=BRAND_DARK, spaceBefore=12, spaceAfter=6),
        'footer': ParagraphStyle('IBfooter',
            fontName='Helvetica', fontSize=8,
            textColor=BRAND_GRAY, alignment=1),
    }


def _kpi_table(label_vals):
    """Horizontal KPI summary row — evenly splits usable width."""
    cols  = len(label_vals)
    w     = USABLE_W / cols

    value_row = [
        Paragraph(str(val), ParagraphStyle('kpiv',
            fontName='Helvetica-Bold', fontSize=14,
            textColor=BRAND_BLUE, alignment=1))
        for _, val in label_vals
    ]
    label_row = [
        Paragraph(lbl, ParagraphStyle('kpil',
            fontName='Helvetica', fontSize=8,
            textColor=BRAND_GRAY, alignment=1))
        for lbl, _ in label_vals
    ]

    t = Table([value_row, label_row], colWidths=[w] * cols)
    t.hAlign = 'LEFT'
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BRAND_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    return t


def _pie_chart(breakdown):
    """Build a pie chart — labels kept short to avoid overlap."""
    if not breakdown:
        return None

    # Sort descending so largest slice is drawn first
    items   = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    labels  = [k for k, _ in items]
    amounts = [v for _, v in items]
    total   = sum(amounts) or 1

    drawing      = Drawing(200, 160)
    pie          = Pie()
    pie.x        = 10
    pie.y        = 10
    pie.width    = 110
    pie.height   = 110

    pie.data     = amounts
    # Short label: first 8 chars + percentage
    pie.labels   = [
        '{} {:.0f}%'.format(lbl[:8], amt / total * 100)
        for lbl, amt in zip(labels, amounts)
    ]
    pie.sideLabels          = True
    pie.sideLabelsOffset    = 0.15
    pie.simpleLabels        = False
    pie.slices.strokeWidth  = 0.5
    pie.slices.strokeColor  = colors.white

    for i in range(len(amounts)):
        pie.slices[i].fillColor = colors.HexColor(
            CATEGORY_COLORS[i % len(CATEGORY_COLORS)])

    drawing.add(pie)
    return drawing


def generate_expense_report(user, expenses, from_date, to_date, salary=0):
    """
    Generate a PDF report and return it as a BytesIO buffer.

    Parameters
    ----------
    user      : User ORM object (.username, .email)
    expenses  : list of Expense ORM objects
    from_date : datetime
    to_date   : datetime
    salary    : float

    Returns
    -------
    io.BytesIO  — seek(0) already called
    """
    buf = io.BytesIO()
    s   = _styles()

    doc = SimpleDocTemplate(
        buf,
        pagesize       = A4,
        leftMargin     = L_MARGIN,
        rightMargin    = R_MARGIN,
        # Bring header closer to top for better visual balance.
        topMargin      = 1.2 * cm,
        bottomMargin   = 2 * cm,
        title          = f'Expense Report — {user.username}',
        author         = 'IntelliBudget AI',
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph('IntelliBudget AI', s['title']))
    story.append(Paragraph(
        f'Expense Report  |  {user.username} ({user.email})',
        s['subtitle']))
    story.append(Paragraph(
        f'Period: {from_date.strftime("%d %b %Y")}  to  {to_date.strftime("%d %b %Y")}',
        s['subtitle']))
    # Use an exact-width divider aligned to margins for consistent layout.
    story.append(HRFlowable(width=USABLE_W, thickness=2,
                            color=BRAND_BLUE, spaceAfter=10, hAlign='LEFT'))

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total     = sum(e.amount for e in expenses)
    avg       = total / max(len(expenses), 1)

    breakdown = {}
    for e in expenses:
        breakdown[e.category] = breakdown.get(e.category, 0) + e.amount

    top_cat = max(breakdown, key=breakdown.get) if breakdown else 'N/A'

    story.append(_kpi_table([
        ('Total Spent',        f'{CURRENCY}{total:,.2f}'),
        ('Transactions',       str(len(expenses))),
        ('Avg / Transaction',  f'{CURRENCY}{avg:,.2f}'),
        ('Top Category',       top_cat),
    ]))
    story.append(Spacer(1, 14))

    # ── Category Breakdown ────────────────────────────────────────────────────
    story.append(Paragraph('Category Breakdown', s['heading']))

    pie = _pie_chart(breakdown)

    # ── Category table: 3 columns ────────────────────────────────────────────
    # IMPORTANT: when used side-by-side with the pie, the available width for
    # this table is (USABLE_W - pie_width). So colWidths must be computed from
    # that, otherwise the table overflows and alignment looks broken.
    pie_w          = 200
    available_cat_w = USABLE_W if not pie else (USABLE_W - pie_w)

    # Allocate widths proportionally: Category 50%, Amount 30%, % Share 20%
    cat_col_w = [
        available_cat_w * 0.50,
        available_cat_w * 0.30,
        available_cat_w * 0.20,
    ]

    cat_rows = [['Category', 'Amount', '% Share']]
    for cat in sorted(breakdown, key=breakdown.get, reverse=True):
        pct = breakdown[cat] / total * 100 if total else 0
        cat_rows.append([
            cat,
            f'{CURRENCY}{breakdown[cat]:,.2f}',
            f'{pct:.1f}%',
        ])

    cat_t = Table(cat_rows, colWidths=cat_col_w)
    cat_t.hAlign = 'LEFT'
    cat_t.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1,  0), BRAND_BLUE),
        ('TEXTCOLOR',      (0, 0), (-1,  0), colors.white),
        ('FONTNAME',       (0, 0), (-1,  0), 'Helvetica-Bold'),
        ('FONTSIZE',       (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ('ALIGN',          (0, 0), ( 0, -1), 'LEFT'),
        ('ALIGN',          (1, 0), (-1, -1), 'RIGHT'),
        ('GRID',           (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
        ('TOPPADDING',     (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 5),
    ]))

    if pie:
        # Side-by-side: pie on left, table on right
        side = Table(
            [[pie, cat_t]],
            colWidths=[pie_w, USABLE_W - pie_w],
        )
        side.hAlign = 'LEFT'
        side.setStyle(TableStyle([
            ('VALIGN',  (0, 0), (-1, -1), 'TOP'),
            # Remove default paddings so both blocks align cleanly.
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            # Small gutter between pie and table.
            ('LEFTPADDING',   (1, 0), (1, 0), 10),
        ]))
        story.append(side)
    else:
        story.append(cat_t)

    story.append(Spacer(1, 14))

    # ── Detailed Transactions ─────────────────────────────────────────────────
    story.append(Paragraph('Detailed Transactions', s['heading']))

    # Column widths must sum to USABLE_W (~453pt = ~16cm)
    # Date: 2.5cm | Category: 3cm | Description: 7cm | Amount: 3.5cm
    exp_col_w = [2.5 * cm, 3 * cm, 7 * cm, 3.5 * cm]

    rows = [['Date', 'Category', 'Description', 'Amount']]
    for e in sorted(expenses, key=lambda x: x.date, reverse=True):
        # Strip the ₹ from descriptions if the chatbot stored it
        desc = (e.description or '').replace('\u20b9', 'Rs.')
        desc = desc[:45]   # truncate long descriptions
        rows.append([
            e.date.strftime('%d/%m/%Y'),
            e.category or '—',
            desc or '—',
            f'{CURRENCY}{e.amount:,.2f}',
        ])

    # Totals row
    rows.append(['', '', 'TOTAL', f'{CURRENCY}{total:,.2f}'])

    exp_t = Table(rows, colWidths=exp_col_w, repeatRows=1)
    exp_t.hAlign = 'LEFT'
    exp_t.setStyle(TableStyle([
        ('BACKGROUND',     (0,  0), (-1,  0), BRAND_DARK),
        ('TEXTCOLOR',      (0,  0), (-1,  0), colors.white),
        ('FONTNAME',       (0,  0), (-1,  0), 'Helvetica-Bold'),
        ('FONTSIZE',       (0,  0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0,  1), (-1, -2), [colors.white, ROW_ALT]),
        ('BACKGROUND',     (0, -1), (-1, -1), BRAND_LIGHT),
        ('FONTNAME',       (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN',          (3,  0), ( 3, -1), 'RIGHT'),
        ('ALIGN',          (2, -1), ( 2, -1), 'RIGHT'),   # "TOTAL" label
        ('GRID',           (0,  0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
        ('TOPPADDING',     (0,  0), (-1, -1), 5),
        ('BOTTOMPADDING',  (0,  0), (-1, -1), 5),
        ('WORDWRAP',       (2,  1), ( 2, -2), True),
    ]))
    story.append(exp_t)
    story.append(Spacer(1, 20))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=0.5,
                             color=BRAND_GRAY, spaceAfter=6))
    story.append(Paragraph(
        f'Generated by IntelliBudget AI  |  '
        f'{datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")}',
        s['footer']))

    doc.build(story)
    buf.seek(0)
    return buf
