import resend
from app.core.config import settings

resend.api_key = settings.RESEND_API_KEY


def send_email(to: str, subject: str, html: str) -> dict:
    return resend.Emails.send({
        "from": settings.RESEND_FROM_EMAIL,
        "to": to,
        "subject": subject,
        "html": html,
    })


def send_invoice_email(to: str, invoice_number: str, pdf_url: str) -> dict:
    html = f"""
    <h2>Invoice {invoice_number}</h2>
    <p>Please find your invoice attached.</p>
    <p><a href="{pdf_url}">Download Invoice</a></p>
    """
    return send_email(to=to, subject=f"Invoice {invoice_number}", html=html)
