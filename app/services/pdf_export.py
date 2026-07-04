import os
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models.request import ApprovalStep, Attachment, Request
from app.services.approval_chains import get_effective_amount

_LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "ibedc-logo.png")

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

_MARGIN = 40
_PAGE_W, _PAGE_H = letter


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


def generate_request_pdf(
    req: Request, steps: list[ApprovalStep], attachments: list[Attachment]
) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    y = _PAGE_H - _MARGIN

    # ── Header: logo + org name + reference/status ─────────────────────────
    if os.path.exists(_LOGO_PATH):
        try:
            c.drawImage(
                ImageReader(_LOGO_PATH),
                _MARGIN,
                y - 34,
                width=34,
                height=34,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 14)
    c.drawString(_MARGIN + 42, y - 14, "IBEDC")
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(_MARGIN + 42, y - 26, "Invoice Submitter Form")

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0f4c5c"))
    c.drawRightString(_PAGE_W - _MARGIN, y - 12, req.reference or req.id)

    status_label = _STATUS_LABELS.get(req.status, req.status)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#0f4c5c"))
    box_w = c.stringWidth(status_label, "Helvetica-Bold", 8) + 14
    c.roundRect(_PAGE_W - _MARGIN - box_w, y - 30, box_w, 14, 3, stroke=1, fill=0)
    c.drawCentredString(_PAGE_W - _MARGIN - box_w / 2, y - 26, status_label)

    y -= 46
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
    y -= 20

    # ── Title + amount ───────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(_MARGIN, y, req.subject or "")

    amount = get_effective_amount(req)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(_PAGE_W - _MARGIN, y, _fmt_amount(amount, req.currency))
    y -= 22

    # ── Summary field grid ───────────────────────────────────────────────────
    fields: list[tuple[str, str]] = [
        ("Contractor Name", getattr(req, "contractor_name", None) or "—"),
        ("PO / Contract Number", req.po_number or "—"),
        ("Requesting Department", req.project_owner_department or req.department or "—"),
        ("Service Order", getattr(req, "service_order_name", None) or "—"),
        ("Invoice Number", getattr(req, "invoice_number", None) or "—"),
        ("Invoice Date", _fmt_date(getattr(req, "invoice_date", None))),
        (
            "Payment Timeframe",
            f"{req.payment_timeframe_days} days" if getattr(req, "payment_timeframe_days", None) else "—",
        ),
        ("Payment Option", _PAYMENT_OPTION_LABELS.get(getattr(req, "payment_option", None), "—")),
        ("Service Status", _SERVICE_STATUS_LABELS.get(getattr(req, "service_status", None), "—")),
        ("TIN", getattr(req, "tin", None) or "—"),
        ("Documents Confirmed", "Yes" if getattr(req, "documents_confirmed", False) else "No"),
        ("Requested By", req.requested_by),
        ("Created", _fmt_date(req.created_at)),
        ("Attachments", str(len(attachments))),
    ]

    cols = 3
    col_w = (_PAGE_W - 2 * _MARGIN) / cols
    row_h = 28
    for i, (label, value) in enumerate(fields):
        col = i % cols
        row = i // cols
        x = _MARGIN + col * col_w
        fy = y - row * row_h
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.HexColor("#94a3b8"))
        c.drawString(x, fy, label.upper())
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(colors.HexColor("#1e293b"))
        c.drawString(x, fy - 11, str(value)[:42])

    rows_used = -(-len(fields) // cols)
    y -= rows_used * row_h + 10

    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
    y -= 18

    # ── Approval trail (stamp boxes) ────────────────────────────────────────
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(_MARGIN, y, "Approval Trail")
    y -= 14

    acted_steps = [s for s in steps if s.acted_by_name]
    box_cols = 2
    gap = 10
    box_w = (_PAGE_W - 2 * _MARGIN - gap) / box_cols
    box_h = 46

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

        c.setStrokeColor(border)
        c.setLineWidth(1)
        c.rect(x, by, box_w, box_h, stroke=1, fill=0)

        pad = 6
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(border)
        c.drawString(x + pad, by + box_h - 12, step.acted_by_name or "")

        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(x + pad, by + box_h - 22, _fmt_datetime(step.acted_at))

        role_label = _ROLE_LABELS.get(step.role, step.role)
        decision = "Reservation" if step.reservation else _STATUS_LABELS.get(step.status, step.status)
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(x + pad, by + box_h - 32, f"{role_label} · {decision}")

        if step.comment:
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.HexColor("#334155"))
            comment = step.comment if len(step.comment) <= 70 else step.comment[:67] + "..."
            c.drawString(x + pad, by + 6, f"Comment: {comment}")

    rows_used_steps = -(-len(acted_steps) // box_cols) if acted_steps else 0
    y -= rows_used_steps * (box_h + gap) + 6

    if not acted_steps:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.HexColor("#94a3b8"))
        c.drawString(_MARGIN, y, "No approval action recorded yet.")
        y -= 20

    # ── Final decision box ───────────────────────────────────────────────────
    final_step = acted_steps[-1] if acted_steps and req.status in ("approved", "rejected") else None
    if final_step:
        y -= 8
        box_h2 = 56
        c.setStrokeColor(colors.HexColor("#0f4c5c"))
        c.setLineWidth(1.2)
        c.rect(_MARGIN, y - box_h2, _PAGE_W - 2 * _MARGIN, box_h2, stroke=1, fill=0)

        label = "Final Approval" if req.status == "approved" else "Final Rejection"
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0f4c5c"))
        c.drawString(_MARGIN + 8, y - 14, label)

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(_MARGIN + 8, y - 28, final_step.acted_by_name or "")

        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(_MARGIN + 8, y - 40, _fmt_datetime(final_step.acted_at))

        if final_step.comment:
            c.setFont("Helvetica", 7.5)
            c.setFillColor(colors.HexColor("#334155"))
            comment = final_step.comment if len(final_step.comment) <= 110 else final_step.comment[:107] + "..."
            c.drawString(_MARGIN + 8, y - 50, comment)

        y -= box_h2 + 12

    # ── Footer ───────────────────────────────────────────────────────────────
    c.setFont("Helvetica", 6.5)
    c.setFillColor(colors.HexColor("#94a3b8"))
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")
    c.drawString(_MARGIN, 24, f"Generated {generated} · IBEDC Invoice ERP")

    c.showPage()
    c.save()
    return buf.getvalue()
