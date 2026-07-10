import html as html_lib

import resend

from app.core.config import settings

resend.api_key = settings.RESEND_API_KEY

_BRAND = "#0f4c5c"
_TEXT = "#0f172a"
_MUTED = "#64748b"
_BORDER = "#e4ece9"
_SURFACE = "#f7faf9"


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


def _esc(value: object) -> str:
    return html_lib.escape(str(value))


def _button(label: str, href: str) -> str:
    return (
        f'<a href="{href}" '
        f'style="display:inline-block;background-color:{_BRAND};color:#ffffff;'
        f"text-decoration:none;padding:12px 24px;border-radius:8px;"
        f"font-weight:600;font-size:14px;font-family:Figtree,-apple-system,"
        f"'Segoe UI',Roboto,sans-serif;\">{_esc(label)}</a>"
    )


def _detail_table(rows: list[tuple[str, str | None]]) -> str:
    cells = "".join(
        f"<tr>"
        f'<td style="padding:8px 16px 8px 0;color:{_MUTED};font-size:13px;'
        f'white-space:nowrap;vertical-align:top;">{_esc(label)}</td>'
        f'<td style="padding:8px 0;color:{_TEXT};font-size:13px;font-weight:600;">{_esc(value)}</td>'
        f"</tr>"
        for label, value in rows
        if value
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_BORDER};border-radius:8px;margin:20px 0;">'
        f'<tr><td style="padding:4px 16px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cells}</table>'
        f"</td></tr></table>"
    )


def _shell(preheader: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>IBEDC Invoicing Platform</title>
  </head>
  <body style="margin:0;padding:0;background-color:{_SURFACE};font-family:Figtree,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <span style="display:none;font-size:1px;color:{_SURFACE};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">{_esc(preheader)}</span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_SURFACE};padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background-color:#ffffff;border-radius:12px;border:1px solid {_BORDER};">
            <tr>
              <td style="background-color:{_BRAND};padding:18px 32px;border-radius:12px 12px 0 0;">
                <span style="color:#ffffff;font-size:14px;font-weight:600;letter-spacing:0.03em;">IBEDC &middot; INVOICING PLATFORM</span>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;color:{_TEXT};font-size:14px;line-height:1.6;">
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="padding:18px 32px;border-top:1px solid {_BORDER};">
                <p style="margin:0;font-size:12px;color:{_MUTED};">This is an automated message from the IBEDC Invoicing Platform. Please do not reply directly to this email.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def send_invoice_email(to: str, invoice_number: str, pdf_url: str) -> dict:
    body = f"""
    <h2 style="margin:0 0 12px;font-size:18px;color:{_TEXT};">Invoice {_esc(invoice_number)}</h2>
    <p style="margin:0 0 20px;color:{_MUTED};">Please find your invoice attached.</p>
    {_button("Download Invoice", pdf_url)}
    """
    return send_email(
        to=to,
        subject=f"Invoice {invoice_number}",
        html=_shell(f"Invoice {invoice_number}", body),
    )


def send_welcome_email(
    to: str,
    name: str,
    initial_password: str,
    login_link: str,
) -> dict:
    credentials_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_BORDER};border-radius:8px;margin:0 0 20px;">'
        f'<tr><td style="padding:14px 16px;">'
        f'<p style="margin:0 0 8px;font-size:13px;color:{_MUTED};">Email</p>'
        f'<p style="margin:0 0 12px;font-size:14px;font-weight:600;color:{_TEXT};">{_esc(to)}</p>'
        f'<p style="margin:0 0 8px;font-size:13px;color:{_MUTED};">Password</p>'
        f'<p style="margin:0;font-size:14px;font-weight:600;color:{_TEXT};font-family:monospace;">{_esc(initial_password)}</p>'
        f"</td></tr></table>"
    )
    body = f"""
    <h2 style="margin:0 0 12px;font-size:18px;color:{_TEXT};">Welcome to the IBEDC Invoicing Platform</h2>
    <p style="margin:0 0 4px;color:{_MUTED};">Hi {_esc(name)}, an account has been created for you. Use the credentials below to sign in.</p>
    {credentials_block}
    {_button("Sign in", login_link)}
    <p style="margin:24px 0 0;font-size:12px;color:{_MUTED};">Please don&rsquo;t share this email — treat it like a password.</p>
    """
    return send_email(
        to=to,
        subject="Welcome to the IBEDC Invoicing Platform",
        html=_shell("Your account is ready", body),
    )


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
    details = _detail_table(
        [
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
    )
    note_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_BORDER};border-radius:8px;margin:0 0 20px;">'
        f'<tr><td style="padding:14px 16px;">'
        f'<p style="margin:0 0 4px;font-size:13px;font-weight:600;color:{_TEXT};">Message from {_esc(requester_name)}</p>'
        f'<p style="margin:0;font-size:13px;color:{_MUTED};white-space:pre-wrap;">{_esc(note)}</p>'
        f"</td></tr></table>"
        if note
        else ""
    )
    body = f"""
    <h2 style="margin:0 0 12px;font-size:18px;color:{_TEXT};">Clarification requested</h2>
    <p style="margin:0 0 4px;color:{_MUTED};">{_esc(requester_name)} is requesting clarification on the invoice below.</p>
    {details}
    {note_block}
    <p style="margin:0 0 20px;color:{_MUTED};">Click the secure link below to respond — you do not need an account.</p>
    {_button("Respond to this request", link)}
    <p style="margin:24px 0 0;font-size:12px;color:{_MUTED};">This link is unique to you — please don&rsquo;t forward it.</p>
    """
    return send_email(
        to=to,
        subject=f"Clarification requested — {request_reference}",
        html=_shell(f"Clarification requested on {request_reference}", body),
        cc=cc,
    )


def send_clarification_received_email(
    to: str,
    respondent_name: str,
    respondent_position: str,
    clarification_text: str,
    request_reference: str,
    request_subject: str,
    app_link: str,
    attachment_name: str | None = None,
) -> dict:
    details = _detail_table(
        [
            ("Reference", request_reference),
            ("Subject", request_subject),
            ("Respondent", f"{respondent_name} — {respondent_position}"),
            ("Attachment", attachment_name),
        ]
    )
    response_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_BORDER};border-radius:8px;margin:0 0 20px;">'
        f'<tr><td style="padding:14px 16px;">'
        f'<p style="margin:0 0 4px;font-size:13px;font-weight:600;color:{_TEXT};">Response</p>'
        f'<p style="margin:0;font-size:13px;color:{_MUTED};white-space:pre-wrap;">{_esc(clarification_text)}</p>'
        f"</td></tr></table>"
    )
    body = f"""
    <h2 style="margin:0 0 12px;font-size:18px;color:{_TEXT};">Clarification received</h2>
    <p style="margin:0 0 4px;color:{_MUTED};">{_esc(respondent_name)} has responded to your clarification request.</p>
    {details}
    {response_block}
    {_button("View in the app", app_link)}
    """
    return send_email(
        to=to,
        subject=f"Clarification received — {request_reference}",
        html=_shell(f"Clarification received on {request_reference}", body),
    )


def send_pending_approvals_reminder_email(
    to: str,
    recipient_name: str,
    requests: list[dict],
    app_link: str,
) -> dict:
    """Digest of everything still sitting in one approver's queue — sent when
    their backlog crosses a threshold, since nothing currently notifies an
    approver the moment a request first lands on them (only the final
    approve/reject decision emails the requester/prior approvers)."""
    rows = "".join(
        f"<tr>"
        f'<td style="padding:10px 12px;border-top:1px solid {_BORDER};font-size:13px;font-weight:600;color:{_TEXT};">{_esc(r["reference"])}</td>'
        f'<td style="padding:10px 12px;border-top:1px solid {_BORDER};font-size:13px;color:{_TEXT};">{_esc(r["subject"])}</td>'
        f'<td style="padding:10px 12px;border-top:1px solid {_BORDER};font-size:13px;color:{_MUTED};">{_esc(r["requested_by"])}</td>'
        f'<td style="padding:10px 12px;border-top:1px solid {_BORDER};font-size:13px;color:{_MUTED};white-space:nowrap;">{_esc(r["created_at"])}</td>'
        f'<td style="padding:10px 12px;border-top:1px solid {_BORDER};font-size:13px;font-weight:600;color:{_TEXT};text-align:right;white-space:nowrap;">{_esc(r["amount"])}</td>'
        f"</tr>"
        for r in requests
    )
    table = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_BORDER};border-radius:8px;margin:16px 0 20px;overflow:hidden;">'
        f'<tr style="background-color:{_SURFACE};">'
        f'<td style="padding:10px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:{_MUTED};">Reference</td>'
        f'<td style="padding:10px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:{_MUTED};">Subject</td>'
        f'<td style="padding:10px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:{_MUTED};">Requested by</td>'
        f'<td style="padding:10px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:{_MUTED};">Created</td>'
        f'<td style="padding:10px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;color:{_MUTED};text-align:right;">Amount</td>'
        f"</tr>{rows}</table>"
    )
    body = f"""
    <h2 style="margin:0 0 12px;font-size:18px;color:{_TEXT};">Hi {_esc(recipient_name)},</h2>
    <p style="margin:0 0 4px;color:{_MUTED};">
        You have <strong style="color:{_TEXT};">{len(requests)} requests</strong> awaiting your review — this is a
        reminder so nothing sits unnoticed in the queue.
    </p>
    {table}
    {_button("Review pending requests", app_link)}
    """
    return send_email(
        to=to,
        subject=f"Reminder: {len(requests)} requests awaiting your approval",
        html=_shell(f"{len(requests)} requests awaiting your approval", body),
    )


_DECISION_COLORS = {"approved": "#059669", "rejected": "#dc2626"}


def send_request_decision_email(
    to: str,
    recipient_name: str,
    decision: str,
    request_reference: str,
    request_subject: str,
    decided_by_name: str,
    decided_by_role_label: str,
    app_link: str,
    comment: str | None = None,
) -> dict:
    """Notifies the requester and every prior approver once a request reaches
    a final decision (approved or rejected) — sent after MD/CFO sign-off."""
    decision_label = decision.capitalize()
    color = _DECISION_COLORS.get(decision, _TEXT)
    details = _detail_table(
        [
            ("Reference", request_reference),
            ("Subject", request_subject),
            ("Decision", decision_label),
            ("Decided by", f"{decided_by_name} — {decided_by_role_label}"),
        ]
    )
    comment_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_BORDER};border-radius:8px;margin:0 0 20px;">'
        f'<tr><td style="padding:14px 16px;">'
        f'<p style="margin:0 0 4px;font-size:13px;font-weight:600;color:{_TEXT};">Comment</p>'
        f'<p style="margin:0;font-size:13px;color:{_MUTED};white-space:pre-wrap;">{_esc(comment)}</p>'
        f"</td></tr></table>"
        if comment
        else ""
    )
    body = f"""
    <h2 style="margin:0 0 12px;font-size:18px;color:{_TEXT};">Hi {_esc(recipient_name)},</h2>
    <p style="margin:0 0 4px;color:{_MUTED};">
        Request <strong style="color:{_TEXT};">{_esc(request_reference)}</strong> has been
        <strong style="color:{color};">{_esc(decision_label.lower())}</strong>.
    </p>
    {details}
    {comment_block}
    {_button("View in the app", app_link)}
    """
    return send_email(
        to=to,
        subject=f"Request {decision_label} — {request_reference}",
        html=_shell(f"Request {decision_label.lower()} — {request_reference}", body),
    )
