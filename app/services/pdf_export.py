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

_CURRENCY_SYMBOLS = {
    # The Naira sign (U+20A6) isn't in the embedded Figtree font's glyph set —
    # it rendered as a box in the PDF. "NGN" reads unambiguously and avoids
    # depending on font glyph coverage entirely.
    "NGN": "NGN ",
    "USD": "$",
    "GBP": "£",
}
_PAYMENT_OPTION_LABELS = {"arrears": "Arrears", "advance": "Advance"}
_SERVICE_STATUS_LABELS = {"completed": "Completed", "milestone": "Milestone"}
_REQUEST_TYPE_TITLES = {
    "project_payment": "Contractor Invoice Processing Form",
    "advance": "Cash Advance Request Form",
    "expense": "State of Expense Form",
    "proposal": "I Owe You (IOU) Form",
}
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
    "md": "Managing Director",
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
    return value.strftime("%d %b %Y, %I:%M:%S %p")


def _fmt_amount(amount: float, currency: str) -> str:
    symbol = _CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{symbol}{amount:,.2f}"


def _fmt_requested_at(req: Request) -> str:
    return _fmt_datetime(req.submitted_at or req.created_at)


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


def _build_fields(req: Request, amount: float) -> list[tuple[str, str, str | None]]:
    """Field grid is unique per form type — a Cash Advance PDF has no PO/invoice
    fields to show, just as an Invoice PDF has no bank-account fields to show."""
    if req.type == "project_payment":
        return [
            (
                "Contractor Name",
                getattr(req, "contractor_name", None) or "—",
                "Entities must be in capital letters",
            ),
            ("PO / Contract Number", req.po_number or "—", None),
            (
                "Requesting Department",
                req.project_owner_department or req.department or "—",
                "Select from list",
            ),
            ("Invoice Number", getattr(req, "invoice_number", None) or "—", None),
            ("Invoice Amount", _fmt_amount(amount, req.currency), None),
            ("Invoice Date", _fmt_date(getattr(req, "invoice_date", None)), None),
            (
                "Payment Timeframe",
                f"{req.payment_timeframe_days} days"
                if getattr(req, "payment_timeframe_days", None)
                else "—",
                None,
            ),
            (
                "Payment Option",
                _PAYMENT_OPTION_LABELS.get(getattr(req, "payment_option", None), "—"),
                "Select from list",
            ),
            (
                "Service Status",
                _SERVICE_STATUS_LABELS.get(getattr(req, "service_status", None), "—"),
                "Select from list",
            ),
            (
                "TIN",
                getattr(req, "tin", None) or "—",
                "Tax Identification Number (where applicable)",
            ),
            (
                "Documents Confirmed",
                "Yes" if getattr(req, "documents_confirmed", False) else "No",
                "Select from list",
            ),
            ("Requested By", req.requested_by, None),
            ("Created", _fmt_date(req.created_at), None),
        ]

    if req.type in ("advance", "expense"):
        is_advance = req.type == "advance"
        detail_label = "Advance Details" if is_advance else "Expense Details"
        detail_value = (
            getattr(req, "advance_details" if is_advance else "expense_details", None)
            or "—"
        )
        return [
            ("Department", req.department or "—", None),
            (detail_label, detail_value, None),
            ("Amount", _fmt_amount(amount, req.currency), None),
            ("Bank Name", getattr(req, "bank_name", None) or "—", None),
            ("Account Name", getattr(req, "account_name", None) or "—", None),
            ("Account Number", getattr(req, "account_no", None) or "—", None),
            ("Requested By", req.requested_by, None),
            ("Created", _fmt_date(req.created_at), None),
        ]

    if req.type == "proposal":
        return [
            ("Department", req.department or "—", None),
            ("Purpose", getattr(req, "purpose", None) or "—", None),
            ("Amount Proposed", _fmt_amount(amount, req.currency), None),
            ("Bank Name", getattr(req, "bank_name", None) or "—", None),
            ("Account Name", getattr(req, "account_name", None) or "—", None),
            ("Account Number", getattr(req, "account_no", None) or "—", None),
            ("Requested By", req.requested_by, None),
            ("Created", _fmt_date(req.created_at), None),
        ]

    return [
        ("Requested By", req.requested_by, None),
        ("Created", _fmt_date(req.created_at), None),
    ]


def generate_request_pdf(
    req: Request, steps: list[ApprovalStep], attachments: list[Attachment]
) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    y = _PAGE_H - _MARGIN

    # ── Header: centered company block, corner reference tag ───────────────
    header_h = 78
    c.setFillColor(colors.HexColor("#f7faf9"))
    c.rect(0, y - header_h + 14, _PAGE_W, header_h, stroke=0, fill=1)

    logo_size = 30
    if os.path.exists(_LOGO_PATH):
        try:
            c.drawImage(
                ImageReader(_LOGO_PATH),
                _PAGE_W / 2 - logo_size / 2,
                y - 10,
                width=logo_size,
                height=logo_size,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    c.setFont(_FONT_BOLD, 17)
    c.setFillColor(_BRAND)
    c.drawCentredString(_PAGE_W / 2, y - 26, "IBEDC")
    c.setFont(_FONT_REGULAR, 9)
    c.setFillColor(_SLATE)
    c.drawCentredString(_PAGE_W / 2, y - 39, "Contractor Invoice Processing Form")

    # Reference / requester tag, top-right corner
    c.setFont(_FONT_BOLD, 10.5)
    c.setFillColor(_BRAND)
    c.drawRightString(_PAGE_W - _MARGIN - 56, y - 4, req.reference or req.id)
    c.setFont(_FONT_REGULAR, 7.5)
    c.setFillColor(_MUTED)
    c.drawRightString(
        _PAGE_W - _MARGIN - 56, y - 16, f"Requested by {req.requested_by}"
    )
    c.drawRightString(_PAGE_W - _MARGIN - 56, y - 26, _fmt_requested_at(req))

    status_color = _STAMP_COLORS.get(req.status, _SLATE)
    _draw_stamp(
        c,
        _PAGE_W - _MARGIN - 24,
        y - 8,
        _STATUS_LABELS.get(req.status, req.status),
        "IBEDC",
        status_color,
        radius=26,
    )

    y -= header_h + 4
    c.setStrokeColor(_HAIRLINE)
    c.setLineWidth(0.75)
    c.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
    y -= 20

    # ── Title ────────────────────────────────────────────────────────────────
    c.setFont(_FONT_BOLD, 13)
    c.setFillColor(_INK)
    c.drawString(_MARGIN, y, req.subject or "")
    y -= 26

    # ── Open field layout: label above value, italic hint below ────────────
    amount = get_effective_amount(req)
    attachment_names = ", ".join(a.name for a in attachments) if attachments else "—"

    fields: list[tuple[str, str, str | None]] = [
        (
            "Contractor Name",
            getattr(req, "contractor_name", None) or "—",
            "Entities must be in capital letters",
        ),
        ("PO / Contract Number", req.po_number or "—", None),
        (
            "Requesting Department",
            req.project_owner_department or req.department or "—",
            "Select from list",
        ),
        ("Invoice Number", getattr(req, "invoice_number", None) or "—", None),
        ("Invoice Amount", _fmt_amount(amount, req.currency), None),
        ("Invoice Date", _fmt_date(getattr(req, "invoice_date", None)), None),
        (
            "Payment Timeframe",
            f"{req.payment_timeframe_days} days"
            if getattr(req, "payment_timeframe_days", None)
            else "—",
            None,
        ),
        (
            "Payment Option",
            _PAYMENT_OPTION_LABELS.get(getattr(req, "payment_option", None), "—"),
            "Select from list",
        ),
        (
            "Service Status",
            _SERVICE_STATUS_LABELS.get(getattr(req, "service_status", None), "—"),
            "Select from list",
        ),
        (
            "TIN",
            getattr(req, "tin", None) or "—",
            "Tax Identification Number (where applicable)",
        ),
        (
            "Documents Confirmed",
            "Yes" if getattr(req, "documents_confirmed", False) else "No",
            "Select from list",
        ),
        ("Requested By", req.requested_by, None),
        ("Created", _fmt_date(req.created_at), None),
    ]

    cols = 2
    col_w = (_PAGE_W - 2 * _MARGIN) / cols
    row_h = 34
    rows_used = -(-len(fields) // cols)

    for i, (label, value, hint) in enumerate(fields):
        col = i % cols
        row = i // cols
        x = _MARGIN + col * col_w
        fy = y - row * row_h
        c.setFont(_FONT_REGULAR, 6.5)
        c.setFillColor(_MUTED)
        c.drawString(x, fy, label.upper())
        c.setFont(_FONT_SEMIBOLD, 9.5)
        c.setFillColor(colors.HexColor("#1e293b"))
        c.drawString(x, fy - 13, str(value)[:46])
        if hint:
            c.setFont("Helvetica-Oblique", 6)
            c.setFillColor(_MUTED)
            c.drawString(x, fy - 23, hint)

    y -= rows_used * row_h + 10

    # ── Attachments, styled as a link field ─────────────────────────────────
    c.setFont(_FONT_REGULAR, 6.5)
    c.setFillColor(_MUTED)
    c.drawString(_MARGIN, y, "ATTACH INVOICE")
    c.setFont(_FONT_SEMIBOLD, 8.5)
    c.setFillColor(colors.HexColor("#2563eb"))
    c.drawString(_MARGIN, y - 13, attachment_names[:90])
    y -= 30

    # ── Approval trail (stamp boxes) ────────────────────────────────────────
    c.setFont(_FONT_BOLD, 10.5)
    c.setFillColor(_INK)
    c.drawString(_MARGIN, y, "Approval Trail")
    y -= 16

    acted_steps = [s for s in steps if s.acted_by_name]
    is_final_decision = acted_steps and req.status in ("approved", "rejected")
    # The last acted step is re-shown below as the Final Approval/Rejection
    # callout, so leave it out of the trail grid to avoid showing it twice.
    trail_steps = acted_steps[:-1] if is_final_decision else acted_steps

    box_cols = 2
    gap = 10
    box_w = (_PAGE_W - 2 * _MARGIN - gap) / box_cols
    box_h = 48

    for i, step in enumerate(trail_steps):
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

    rows_used_steps = -(-len(trail_steps) // box_cols) if trail_steps else 0
    y -= rows_used_steps * (box_h + gap) + 8

    if not trail_steps and not is_final_decision:
        c.setFont(_FONT_REGULAR, 8)
        c.setFillColor(_MUTED)
        c.drawString(_MARGIN, y, "No approval action recorded yet.")
        y -= 22

    # ── Final decision: name/timestamp + a real ink stamp ───────────────────
    final_step = acted_steps[-1] if is_final_decision else None
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


def _draw_report_header(
    c: canvas.Canvas, period_label: str, generated_at: str
) -> float:
    """Draws the report's page header (used on every page) and returns the y to start the table body at."""
    y = _PAGE_H - _MARGIN
    header_h = 68

    c.setFillColor(colors.HexColor("#f7faf9"))
    c.rect(0, y - header_h + 14, _PAGE_W, header_h, stroke=0, fill=1)

    logo_size = 26
    if os.path.exists(_LOGO_PATH):
        try:
            c.drawImage(
                ImageReader(_LOGO_PATH),
                _PAGE_W / 2 - logo_size / 2,
                y - 8,
                width=logo_size,
                height=logo_size,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    c.setFont(_FONT_BOLD, 15)
    c.setFillColor(_BRAND)
    c.drawCentredString(_PAGE_W / 2, y - 22, "IBEDC")
    c.setFont(_FONT_REGULAR, 8.5)
    c.setFillColor(_SLATE)
    c.drawCentredString(_PAGE_W / 2, y - 34, "Approved Invoices Report")

    # Period / generated tag, top-right corner (mirrors the request form's ref tag)
    c.setFont(_FONT_BOLD, 9.5)
    c.setFillColor(_BRAND)
    c.drawRightString(_PAGE_W - _MARGIN, y - 4, period_label)
    c.setFont(_FONT_REGULAR, 7)
    c.setFillColor(_MUTED)
    c.drawRightString(_PAGE_W - _MARGIN, y - 15, f"Generated {generated_at}")

    y -= header_h + 4
    c.setStrokeColor(_HAIRLINE)
    c.setLineWidth(0.75)
    c.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
    return y - 18


_REPORT_COLUMNS = [
    ("Reference", 0.16),
    ("Approved", 0.11),
    ("Subject / Contractor", 0.29),
    ("Department", 0.18),
    ("Requested By", 0.14),
    ("Amount", 0.12),
]


def _draw_report_table_head(c: canvas.Canvas, y: float) -> float:
    x = _MARGIN
    total_w = _PAGE_W - 2 * _MARGIN
    c.setFont(_FONT_SEMIBOLD, 7)
    c.setFillColor(_MUTED)
    for label, frac in _REPORT_COLUMNS:
        c.drawString(x, y, label.upper())
        x += total_w * frac
    y -= 8
    c.setStrokeColor(_HAIRLINE)
    c.setLineWidth(0.75)
    c.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
    return y - 12


def generate_period_report_pdf(requests: list[Request], period_label: str) -> bytes:
    """
    A reconciliation report — every request matching the caller's filters (typically
    status=approved for a given month) as one flowing table, not one PDF per invoice.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    generated_at = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")

    totals_by_currency: dict[str, float] = {}
    for req in requests:
        amt = get_effective_amount(req)
        totals_by_currency[req.currency] = (
            totals_by_currency.get(req.currency, 0.0) + amt
        )

    y = _draw_report_header(c, period_label, generated_at)

    c.setFont(_FONT_BOLD, 9)
    c.setFillColor(_INK)
    summary = (
        f"{len(requests)} request{'s' if len(requests) != 1 else ''} · "
        + ", ".join(
            _fmt_amount(total, currency)
            for currency, total in totals_by_currency.items()
        )
        if requests
        else f"{len(requests)} requests"
    )
    c.drawString(_MARGIN, y, summary)
    y -= 20

    y = _draw_report_table_head(c, y)

    row_h = 26
    total_w = _PAGE_W - 2 * _MARGIN

    for req in sorted(requests, key=lambda r: r.closed_at or r.updated_at):
        if y < _MARGIN + row_h:
            c.showPage()
            y = _draw_report_header(c, period_label, generated_at)
            y = _draw_report_table_head(c, y)

        contractor_or_subject = (
            getattr(req, "contractor_name", None) or req.subject or ""
        )
        x = _MARGIN

        cells = [
            req.reference or req.id,
            _fmt_date(req.closed_at or req.updated_at),
            contractor_or_subject[:34],
            (req.project_owner_department or req.department or "")[:22],
            req.requested_by[:20],
            _fmt_amount(get_effective_amount(req), req.currency),
        ]
        c.setFont(_FONT_REGULAR, 7.5)
        c.setFillColor(colors.HexColor("#1e293b"))
        for (_, frac), value in zip(_REPORT_COLUMNS, cells):
            c.drawString(x, y, str(value))
            x += total_w * frac

        y -= 8
        c.setStrokeColor(colors.HexColor("#f1f5f9"))
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
        y -= row_h - 8

    if not requests:
        c.setFont(_FONT_REGULAR, 8)
        c.setFillColor(_MUTED)
        c.drawString(_MARGIN, y, "No requests match this period.")

    c.showPage()
    c.save()
    return buf.getvalue()
