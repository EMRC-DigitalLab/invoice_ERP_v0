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
) -> dict:
    html = f"""
    <h2>Clarification requested — {request_reference}</h2>
    <p>{requester_name} is requesting clarification on <strong>{request_subject}</strong> ({request_reference}).</p>
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
