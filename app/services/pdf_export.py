import os
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.models.request import ApprovalStep, Attachment, Request
from app.services.approval_chains import get_effective_amount

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
_LOGO_PATH = os.path.join(_ASSETS_DIR, "ibedc-logo.png")
_FONTS_DIR = os.path.join(_ASSETS_DIR, "fonts")

_FONT_REGULAR = "Helvetica"
_FONT_SEMIBOLD = "Helvetica-Bold"
_FONT_BOLD = "Helvetica-Bold"

try:
    pdfmetrics.registerFont(
        TTFont("Figtree", os.path.join(_FONTS_DIR, "Figtree-Regular.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont("Figtree-SemiBold", os.path.join(_FONTS_DIR, "Figtree-SemiBold.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont("Figtree-Bold", os.path.join(_FONTS_DIR, "Figtree-Bold.ttf"))
    )
    _FONT_REGULAR = "Figtree"
    _FONT_SEMIBOLD = "Figtree-SemiBold"
    _FONT_BOLD = "Figtree-Bold"
except Exception:
    pass  # Falls back to the base-14 Helvetica family if the font files are missing.

_CURRENCY_SYMBOLS = {"NGN": "₦", "USD": "$", "GBP": "£"}
_PAYMENT_OPTION_LABELS = {"arrears": "Arrears", "advance": "Advance"}
_SERVICE_STATUS_LABELS = {"completed": "Completed", "milestone": "Milestone"}
_ROLE_LABELS = {
    "staff": "Staff",
    "executive_assistant": "Executive Assistant",
    "department_head": "Department Head",
    "regional_department_head": "Regional Department Head",
    "regional_manager": "Regional Manager",
    "finance_controller": "Finance Controller",
    "finance_control": "Finance & Control",
    "project_owner": "Project Owner",
    "procurement": "Procurement",
    "cfo": "CFO",
}
_STATUS_LABELS = {
    "draft": "Draft",
    "in_review": "In Review",
    "approved": "Approved",
    "returned": "Returned",
    "rejected": "Rejected",
    "closed": "Closed",
}
_STAMP_COLORS = {
    "draft": colors.HexColor("#64748b"),
    "in_review": colors.HexColor("#d97706"),
    "approved": colors.HexColor("#059669"),
    "returned": colors.HexColor("#ea580c"),
    "rejected": colors.HexColor("#dc2626"),
    "closed": colors.HexColor("#0369a1"),
}

_MARGIN = 42
_PAGE_W, _PAGE_H = letter
_INK = colors.HexColor("#0f172a")
_MUTED = colors.HexColor("#94a3b8")
_SLATE = colors.HexColor("#475569")
_HAIRLINE = colors.HexColor("#e2e8f0")
_BRAND = colors.HexColor("#0f4c5c")


def _fmt_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value.strftime("%d %b %Y")


def _fmt_datetime(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value.strftime("%d %b %Y, %I:%M %p")


def _fmt_amount(amount: float, currency: str) -> str:
    symbol = _CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{symbol}{amount:,.2f}"


def _draw_stamp(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    label: str,
    sublabel: str,
    color,
    radius: float = 34,
) -> None:
    """
    Draws a circular ink-stamp graphic: a double ring, rotated bold caption,
    and a smaller line underneath — evokes a real rubber approval stamp
    rather than a plain status pill.
    """
    c.saveState()
    c.translate(cx, cy)
    c.rotate(-10)
    c.setFillAlpha(0.9)
    c.setStrokeAlpha(0.9)

    c.setStrokeColor(color)
    c.setLineWidth(2.2)
    c.circle(0, 0, radius, stroke=1, fill=0)
    c.setLineWidth(0.8)
    c.circle(0, 0, radius - 4, stroke=1, fill=0)

    c.setFillColor(color)
    label = label.upper()
    max_width = 2 * (radius - 8)
    font_size = min(11, radius * 0.34)
    while font_size > 5 and c.stringWidth(label, _FONT_BOLD, font_size) > max_width:
        font_size -= 0.5
    c.setFont(_FONT_BOLD, font_size)
    c.drawCentredString(0, font_size * 0.25, label)

    sub_size = max(4.2, radius * 0.15)
    c.setFont(_FONT_SEMIBOLD, sub_size)
    c.drawCentredString(0, -font_size * 0.9, sublabel.upper())

    c.restoreState()


def generate_request_pdf(
    req: Request, steps: list[ApprovalStep], attachments: list[Attachment]
) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    y = _PAGE_H - _MARGIN

    # ── Header band ──────────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor("#f7faf9"))
    c.rect(0, y - 50, _PAGE_W, 60, stroke=0, fill=1)

    if os.path.exists(_LOGO_PATH):
        try:
            c.drawImage(
                ImageReader(_LOGO_PATH),
                _MARGIN,
                y - 30,
                width=34,
                height=34,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    c.setFont(_FONT_BOLD, 15)
    c.setFillColor(_BRAND)
    c.drawString(_MARGIN + 42, y - 10, "IBEDC")
    c.setFont(_FONT_REGULAR, 8.5)
    c.setFillColor(_SLATE)
    c.drawString(_MARGIN + 42, y - 23, "Invoice Submitter Form")

    c.setFont(_FONT_BOLD, 11)
    c.setFillColor(_BRAND)
    c.drawRightString(_PAGE_W - _MARGIN - 60, y - 10, req.reference or req.id)
    c.setFont(_FONT_REGULAR, 7.5)
    c.setFillColor(_MUTED)
    c.drawRightString(
        _PAGE_W - _MARGIN - 60, y - 22, f"Requested by {req.requested_by}"
    )

    status_color = _STAMP_COLORS.get(req.status, _SLATE)
    _draw_stamp(
        c,
        _PAGE_W - _MARGIN - 24,
        y - 14,
        _STATUS_LABELS.get(req.status, req.status),
        "IBEDC",
        status_color,
        radius=26,
    )

    y -= 62
    c.setStrokeColor(_HAIRLINE)
    c.setLineWidth(0.75)
    c.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
    y -= 22

    # ── Title + amount ───────────────────────────────────────────────────────
    c.setFont(_FONT_BOLD, 14)
    c.setFillColor(_INK)
    c.drawString(_MARGIN, y, req.subject or "")

    amount = get_effective_amount(req)
    c.setFont(_FONT_BOLD, 14)
    c.drawRightString(_PAGE_W - _MARGIN, y, _fmt_amount(amount, req.currency))
    y -= 24

    # ── Summary field grid ───────────────────────────────────────────────────
    fields: list[tuple[str, str]] = [
        ("Contractor Name", getattr(req, "contractor_name", None) or "—"),
        ("PO / Contract Number", req.po_number or "—"),
        (
            "Requesting Department",
            req.project_owner_department or req.department or "—",
        ),
        ("Service Order", getattr(req, "service_order_name", None) or "—"),
        ("Invoice Number", getattr(req, "invoice_number", None) or "—"),
        ("Invoice Date", _fmt_date(getattr(req, "invoice_date", None))),
        (
            "Payment Timeframe",
            f"{req.payment_timeframe_days} days"
            if getattr(req, "payment_timeframe_days", None)
            else "—",
        ),
        (
            "Payment Option",
            _PAYMENT_OPTION_LABELS.get(getattr(req, "payment_option", None), "—"),
        ),
        (
            "Service Status",
            _SERVICE_STATUS_LABELS.get(getattr(req, "service_status", None), "—"),
        ),
        ("TIN", getattr(req, "tin", None) or "—"),
        (
            "Documents Confirmed",
            "Yes" if getattr(req, "documents_confirmed", False) else "No",
        ),
        ("Requested By", req.requested_by),
        ("Created", _fmt_date(req.created_at)),
        ("Attachments", str(len(attachments))),
    ]

    cols = 3
    col_w = (_PAGE_W - 2 * _MARGIN) / cols
    row_h = 30
    rows_used = -(-len(fields) // cols)

    # Faint field-grid rules, evoking a real form rather than a plain list.
    c.setStrokeColor(_HAIRLINE)
    c.setLineWidth(0.5)
    for row_i in range(rows_used + 1):
        ly = y + 6 - row_i * row_h
        c.line(_MARGIN, ly, _PAGE_W - _MARGIN, ly)
    for col_i in range(1, cols):
        lx = _MARGIN + col_i * col_w
        c.line(lx, y + 6, lx, y + 6 - rows_used * row_h)

    for i, (label, value) in enumerate(fields):
        col = i % cols
        row = i // cols
        x = _MARGIN + col * col_w + 8
        fy = y - row * row_h
        c.setFont(_FONT_REGULAR, 6.5)
        c.setFillColor(_MUTED)
        c.drawString(x, fy, label.upper())
        c.setFont(_FONT_SEMIBOLD, 9)
        c.setFillColor(colors.HexColor("#1e293b"))
        c.drawString(x, fy - 12, str(value)[:40])

    y -= rows_used * row_h + 16

    # ── Approval trail (stamp boxes) ────────────────────────────────────────
    c.setFont(_FONT_BOLD, 10.5)
    c.setFillColor(_INK)
    c.drawString(_MARGIN, y, "Approval Trail")
    y -= 16

    acted_steps = [s for s in steps if s.acted_by_name]
    box_cols = 2
    gap = 10
    box_w = (_PAGE_W - 2 * _MARGIN - gap) / box_cols
    box_h = 48

    for i, step in enumerate(acted_steps):
        col = i % box_cols
        row = i // box_cols
        x = _MARGIN + col * (box_w + gap)
        by = y - row * (box_h + gap) - box_h

        if step.status == "rejected":
            border = colors.HexColor("#ef4444")
        elif step.status == "returned":
            border = colors.HexColor("#f97316")
        elif step.reservation:
            border = colors.HexColor("#d97706")
        else:
            border = colors.HexColor("#2563eb")

        c.setFillColor(colors.Color(border.red, border.green, border.blue, alpha=0.04))
        c.roundRect(x, by, box_w, box_h, 4, stroke=0, fill=1)
        c.setStrokeColor(border)
        c.setLineWidth(1)
        c.roundRect(x, by, box_w, box_h, 4, stroke=1, fill=0)

        pad = 8
        c.setFont(_FONT_BOLD, 9.5)
        c.setFillColor(border)
        c.drawString(x + pad, by + box_h - 14, step.acted_by_name or "")

        c.setFont(_FONT_REGULAR, 7)
        c.setFillColor(_SLATE)
        c.drawString(x + pad, by + box_h - 25, _fmt_datetime(step.acted_at))

        role_label = _ROLE_LABELS.get(step.role, step.role)
        decision = (
            "Reservation"
            if step.reservation
            else _STATUS_LABELS.get(step.status, step.status)
        )
        c.setFont(_FONT_SEMIBOLD, 6.5)
        c.setFillColor(_SLATE)
        c.drawString(x + pad, by + box_h - 35, f"{role_label} · {decision}")

        if step.comment:
            c.setFont(_FONT_REGULAR, 6.5)
            c.setFillColor(colors.HexColor("#334155"))
            comment = (
                step.comment if len(step.comment) <= 68 else step.comment[:65] + "..."
            )
            c.drawString(x + pad, by + 7, f"“{comment}”")

    rows_used_steps = -(-len(acted_steps) // box_cols) if acted_steps else 0
    y -= rows_used_steps * (box_h + gap) + 8

    if not acted_steps:
        c.setFont(_FONT_REGULAR, 8)
        c.setFillColor(_MUTED)
        c.drawString(_MARGIN, y, "No approval action recorded yet.")
        y -= 22

    # ── Final decision: name/timestamp + a real ink stamp ───────────────────
    final_step = (
        acted_steps[-1]
        if acted_steps and req.status in ("approved", "rejected")
        else None
    )
    if final_step:
        y -= 10
        box_h2 = 70
        c.setStrokeColor(_BRAND)
        c.setLineWidth(1.2)
        c.roundRect(
            _MARGIN, y - box_h2, _PAGE_W - 2 * _MARGIN, box_h2, 5, stroke=1, fill=0
        )

        label = "Final Approval" if req.status == "approved" else "Final Rejection"
        c.setFont(_FONT_BOLD, 8.5)
        c.setFillColor(_BRAND)
        c.drawString(_MARGIN + 14, y - 18, label)

        c.setFont(_FONT_BOLD, 11)
        c.setFillColor(_INK)
        c.drawString(_MARGIN + 14, y - 34, final_step.acted_by_name or "")

        role_label = _ROLE_LABELS.get(final_step.role, final_step.role)
        c.setFont(_FONT_REGULAR, 8)
        c.setFillColor(_SLATE)
        c.drawString(
            _MARGIN + 14, y - 47, f"{role_label} · {_fmt_datetime(final_step.acted_at)}"
        )

        if final_step.comment:
            c.setFont(_FONT_REGULAR, 8)
            c.setFillColor(colors.HexColor("#334155"))
            comment = (
                final_step.comment
                if len(final_step.comment) <= 95
                else final_step.comment[:92] + "..."
            )
            c.drawString(_MARGIN + 14, y - 60, f"“{comment}”")

        stamp_color = _STAMP_COLORS.get(req.status, _BRAND)
        stamp_label = "APPROVED" if req.status == "approved" else "REJECTED"
        _draw_stamp(
            c,
            _PAGE_W - _MARGIN - 50,
            y - box_h2 / 2,
            stamp_label,
            _fmt_date(final_step.acted_at),
            stamp_color,
            radius=32,
        )

        y -= box_h2 + 14

    # ── Footer ───────────────────────────────────────────────────────────────
    c.setStrokeColor(_HAIRLINE)
    c.setLineWidth(0.5)
    c.line(_MARGIN, 34, _PAGE_W - _MARGIN, 34)
    c.setFont(_FONT_REGULAR, 6.5)
    c.setFillColor(_MUTED)
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")
    c.drawString(_MARGIN, 22, f"Generated {generated} · IBEDC Invoice ERP")

    c.showPage()
    c.save()
    return buf.getvalue()
