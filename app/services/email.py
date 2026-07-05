import resend

from app.core.config import settings

resend.api_key = settings.RESEND_API_KEY


def send_email(to: str, subject: str, html: str, cc: list[str] | None = None) -> dict:
    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": to,
        "subject": subject,
        "html": html,
    }
    if cc:
        payload["cc"] = cc
    return resend.Emails.send(payload)


def send_invoice_email(to: str, invoice_number: str, pdf_url: str) -> dict:
    html = f"""
    <h2>Invoice {invoice_number}</h2>
    <p>Please find your invoice attached.</p>
    <p><a href="{pdf_url}">Download Invoice</a></p>
    """
    return send_email(to=to, subject=f"Invoice {invoice_number}", html=html)


def send_clarification_request_email(
    to: str,
    cc: list[str] | None,
    requester_name: str,
    request_reference: str,
    request_subject: str,
    link: str,
    contractor_name: str | None = None,
    po_number: str | None = None,
    invoice_number: str | None = None,
    amount_due: float | None = None,
    currency: str | None = None,
    note: str | None = None,
) -> dict:
    detail_rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;">{label}</td>'
        f'<td style="padding:4px 0;font-weight:600;color:#0f172a;">{value}</td></tr>'
        for label, value in [
            ("Reference", request_reference),
            ("Subject", request_subject),
            ("Contractor", contractor_name),
            ("PO Number", po_number),
            ("Invoice Number", invoice_number),
            (
                "Amount Due",
                f"{currency} {amount_due:,.2f}" if amount_due is not None else None,
            ),
        ]
        if value
    )
    note_block = (
        f'<p style="background:#f7faf9;border-radius:8px;padding:12px;">'
        f"<strong>Message from {requester_name}:</strong><br/>{note}</p>"
        if note
        else ""
    )
    html = f"""
    <h2>Clarification requested — {request_reference}</h2>
    <p>{requester_name} is requesting clarification on the invoice below.</p>
    <table style="border-collapse:collapse;margin:16px 0;">{detail_rows}</table>
    {note_block}
    <p>Please click the secure link below to respond. You do not need an account.</p>
    <p><a href="{link}">Respond to this request</a></p>
    <p style="color:#64748b;font-size:12px;">This link is unique to you — please don't forward it.</p>
    """
    return send_email(
        to=to,
        subject=f"Clarification requested — {request_reference}",
        html=html,
        cc=cc,
    )


def send_clarification_received_email(
    to: str,
    respondent_name: str,
    request_reference: str,
    app_link: str,
) -> dict:
    html = f"""
    <h2>Clarification received — {request_reference}</h2>
    <p>{respondent_name} has responded to your clarification request on {request_reference}.</p>
    <p><a href="{app_link}">View the response</a></p>
    """
    return send_email(
        to=to,
        subject=f"Clarification received — {request_reference}",
        html=html,
    )
