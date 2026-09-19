"""
email_utils.py
Shared helper for sending registration/payment emails via Gmail SMTP, used by
select_method_handler.py, mark_paid_handler.py and stripe_webhook_handler.py.

Every chapter-specific detail (event name/date/venue, who to contact, the
WhatsApp link, the invite email's opening paragraphs) comes from
chapter_config.json, which scripts/prepare.py generates from
chapter.config.yaml + content/. Nothing about a particular chapter is written
in this file.

Requires:
  - SENDER_EMAIL env var: the Gmail address to send from (also the SMTP
    username). If unset, sending is skipped entirely (logged, not an error) -
    same graceful-until-configured pattern as Stripe/Venmo/Zelle.
  - GMAIL_APP_PASSWORD env var: a Gmail App Password for that account
    (requires 2-Step Verification enabled on the account; the regular
    account password will not work for SMTP).
"""
import html as _html
import io
import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import qrcode

import chapter_config

GMAIL_USER = os.environ.get("SENDER_EMAIL", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

_CFG = chapter_config.get()
_EVENT = _CFG["event"]
_CONTACT = _CFG["contact"]

EVENT_NAME = _EVENT["name"]
EVENT_DATE = _EVENT["date_label"]
EVENT_DATE_SHORT = _EVENT["date_short"]
EVENT_TIME = _EVENT["time_label"]
VENUE_NAME = _EVENT["venue_name"]
VENUE_ADDRESS = _EVENT["venue_address"]
VENUE_MAPS_URL = _EVENT["venue_maps_url"]
WHATSAPP_GROUP_URL = _CFG["whatsapp_group_url"]
CHAPTER_NAME = _CFG["chapter_name"]
TICKET_QR_PREFIX = "PUNARMILAN-TICKET"


def esc(value):
    """HTML-escape anything that came from a config file or a registrant."""
    return _html.escape(str(value), quote=True)


def _contact_line(prefix):
    """e.g. 'Having trouble with your payment? Contact Alex at +1 ... or a@b.org.'"""
    bits = [esc(_CONTACT["name"])]
    reach = []
    if _CONTACT["phone"]:
        reach.append(esc(_CONTACT["phone"]))
    if _CONTACT["email"]:
        reach.append(f'<a href="mailto:{esc(_CONTACT["email"])}">{esc(_CONTACT["email"])}</a>')
    tail = " or ".join(reach)
    return f"{prefix} Contact {bits[0]}" + (f" at {tail}" if tail else "") + "."


def _footer_html(help_line):
    return f"""
      <hr style="border:none; border-top:1px solid #ddd; margin:24px 0 14px;">
      <p style="font-size:13px; color:#666; margin:0 0 4px;">
        Warm regards,<br>
        <strong>{esc(_CONTACT["name"])}</strong><br>
        {esc(_CONTACT["title"])}, {esc(CHAPTER_NAME)}
      </p>
      <p style="font-size:12.5px; color:#888; margin-top:12px;">
        {help_line}
      </p>
    """


def _whatsapp_html():
    if not WHATSAPP_GROUP_URL:
        return ""
    return (
        f'<p>If you haven\'t joined the WhatsApp group, <a href="{esc(WHATSAPP_GROUP_URL)}">join now</a> for\n'
        "      the latest updates about the event.</p>"
    )


def _directions_html():
    if not VENUE_MAPS_URL:
        return ""
    return f'<br>\n      <a href="{esc(VENUE_MAPS_URL)}">Get directions</a>'


PAYMENT_FOOTER_HTML = _footer_html(_contact_line("Having trouble with your payment?"))
CONFIRMATION_FOOTER_HTML = _footer_html(
    _contact_line("Having trouble with anything else, or a question about refunds and cancellations?")
)
INVITE_FOOTER_HTML = _footer_html(_contact_line("Questions about the event?"))
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _ticket_qr_png_bytes(ticket_code):
    # qrcode.make() defaults to a 1-bit bilevel PNG, which some email
    # clients' image proxies (e.g. Gmail's) fail to render - same failure
    # mode we saw with the Zelle QR asset. Force RGB to match the fix there.
    img = qrcode.make(f"{TICKET_QR_PREFIX}:{ticket_code}", box_size=8, border=1).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _asset_bytes(filename):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def send_email(to_email, subject, html_body, inline_images=None):
    """inline_images: optional dict of {content_id: png_bytes}, referenced in
    html_body as <img src="cid:content_id">.

    Returns (ok: bool, error: str | None) instead of raising, so callers that
    must know whether the email actually went out (e.g. "send instructions"
    is the whole point of that click) can report it accurately, while callers
    for whom email is a side effect of something that already succeeded
    (e.g. a payment) can safely ignore the return value."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        msg = f"GMAIL_USER/GMAIL_APP_PASSWORD not configured - skipping email to {to_email} ({subject!r})."
        print(msg)
        return False, msg
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    msg_alt = MIMEMultipart("alternative")
    msg.attach(msg_alt)
    msg_alt.attach(MIMEText(html_body, "html"))

    for cid, png_bytes in (inline_images or {}).items():
        img = MIMEImage(png_bytes)
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        msg.attach(img)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, [to_email], msg.as_string())
        return True, None
    except Exception as e:
        # Never let an email failure raise into callers for whom email is a
        # side effect (they get (False, ...) back and can choose to ignore it).
        print(f"Gmail SMTP send error for {to_email}: {e}")
        return False, str(e)


def venmo_profile_url(handle):
    return f"https://venmo.com/u/{handle.lstrip('@').strip()}"


def send_payment_instructions_email(reg, method, venmo_handle, zelle_handle):
    name = esc(reg.get("name", ""))
    amount = f"${int(reg['amount_cents']) / 100:.2f}"
    email = reg["email"]

    inline_images = {}
    if method == "venmo" and venmo_handle:
        qr_bytes = _asset_bytes("venmo-qr.png")
        method_html = f"""
          <p><strong>Venmo:</strong> {esc(venmo_handle)}<br>
          {'<img src="cid:qr" alt="Venmo QR code" width="200" height="200"><br>' if qr_bytes else ''}
          <a href="{esc(venmo_profile_url(venmo_handle))}">Open in Venmo</a></p>
        """
        if qr_bytes:
            inline_images["qr"] = qr_bytes
    elif method == "zelle" and zelle_handle:
        qr_bytes = _asset_bytes("zelle-qr.png")
        method_html = f"""
          <p><strong>Zelle:</strong> {esc(zelle_handle)}<br>
          {'<img src="cid:qr" alt="Zelle QR code" width="200" height="200">' if qr_bytes else ''}</p>
        """
        if qr_bytes:
            inline_images["qr"] = qr_bytes
    else:
        return False, "That payment method isn't configured."

    html = f"""
      <p>Hi {name},</p>
      <p>Thanks for registering for {esc(EVENT_NAME)} on {esc(EVENT_DATE)}! To confirm your spot,
      please send <strong>{amount}</strong> via {method.capitalize()}.</p>
      {method_html}
      <p>Please include your full name or email (<strong>{name or esc(email)}</strong>, as entered on
      this registration) in the payment memo so we can match it to your registration.</p>
      <p>Once our team confirms your payment, you'll receive another email confirming your
      registration is complete.</p>
      {PAYMENT_FOOTER_HTML}
    """
    return send_email(email, f"Complete your payment — {EVENT_NAME}", html, inline_images)


def _card_switch_html(checkout_url, card_amount_cents):
    if not (checkout_url and card_amount_cents):
        return ""
    card_amount = f"${card_amount_cents / 100:.2f}"
    return f'<p>Prefer to pay by card instead? <a href="{checkout_url}">Pay {card_amount} by card</a>.</p>'


def _resubmit_switch_html(site_url, email, other_method_label):
    return f"""
      <p>Prefer to pay by {other_method_label} instead? Just head back to the
      <a href="{site_url}">registration page</a> and resubmit the form using the same email
      address (<strong>{esc(email)}</strong>) — you'll be able to choose {other_method_label} from there.</p>
    """


def send_payment_reminder_email(reg, checkout_url, card_amount_cents, site_url, venmo_handle, zelle_handle):
    name = esc(reg.get("name", ""))
    amount = f"${int(reg['amount_cents']) / 100:.2f}"
    email = reg["email"]
    # Lead with whatever method they actually picked, so someone who chose
    # Zelle doesn't get a reminder that only pushes a card link - that's the
    # bug this replaced. Falls back to the card button when they never picked
    # a method (or picked card), same as before.
    method = (reg.get("selected_payment_method") or "").strip().lower()

    inline_images = {}
    if method == "venmo" and venmo_handle:
        qr_bytes = _asset_bytes("venmo-qr.png")
        primary_html = f"""
          <p><strong>Venmo:</strong> {esc(venmo_handle)}<br>
          {'<img src="cid:qr" alt="Venmo QR code" width="200" height="200"><br>' if qr_bytes else ''}
          <a href="{esc(venmo_profile_url(venmo_handle))}">Open in Venmo</a></p>
          <p>Please include your full name or email (<strong>{name or esc(email)}</strong>, as entered on
          this registration) in the payment memo so we can match it to your registration.</p>
        """
        if qr_bytes:
            inline_images["qr"] = qr_bytes
        switch_html = _card_switch_html(checkout_url, card_amount_cents)
        if zelle_handle:
            switch_html += _resubmit_switch_html(site_url, email, "Zelle")
    elif method == "zelle" and zelle_handle:
        qr_bytes = _asset_bytes("zelle-qr.png")
        primary_html = f"""
          <p><strong>Zelle:</strong> {esc(zelle_handle)}<br>
          {'<img src="cid:qr" alt="Zelle QR code" width="200" height="200">' if qr_bytes else ''}</p>
          <p>Please include your full name or email (<strong>{name or esc(email)}</strong>, as entered on
          this registration) in the payment memo so we can match it to your registration.</p>
        """
        if qr_bytes:
            inline_images["qr"] = qr_bytes
        switch_html = _card_switch_html(checkout_url, card_amount_cents)
        if venmo_handle:
            switch_html += _resubmit_switch_html(site_url, email, "Venmo")
    else:
        primary_html = ""
        if checkout_url and card_amount_cents:
            card_amount = f"${card_amount_cents / 100:.2f}"
            primary_html = f"""
              <p style="text-align:center; margin:22px 0;">
                <a href="{checkout_url}" style="display:inline-block; background:#7A2E2E; color:#fff;
                   font-weight:600; font-size:15px; padding:12px 28px; border-radius:5px;
                   text-decoration:none;">Pay {card_amount} by card</a>
              </p>
            """
        switch_html = f"""
          <p>Prefer to pay by Venmo or Zelle instead? Just head back to the
          <a href="{site_url}">registration page</a> and resubmit the form using the same email
          address (<strong>{esc(email)}</strong>) — you'll be able to choose Venmo or Zelle from there.</p>
        """

    html = f"""
      <p>Hi {name},</p>
      <p>Just a friendly reminder — we haven't received your <strong>{amount}</strong> payment yet
      for {esc(EVENT_NAME)} on {esc(EVENT_DATE)}, and wanted to make sure you don't miss your spot.</p>
      {primary_html}
      {switch_html}
      {PAYMENT_FOOTER_HTML}
    """
    return send_email(email, f"Reminder: complete your payment — {EVENT_NAME}", html, inline_images)


def send_registration_confirmed_email(reg):
    name = esc(reg.get("name", ""))
    code = reg.get("ticket_code", "")
    email = reg["email"]
    html = f"""
      <p>Hi {name},</p>
      <p>You're all set! Your payment has been received and your spot for {esc(EVENT_NAME)} on
      {esc(EVENT_DATE)}, {esc(EVENT_TIME)}, is confirmed.</p>
      <p><strong>📍 {esc(VENUE_NAME)}</strong><br>
      {esc(VENUE_ADDRESS)}{_directions_html()}</p>
      {_whatsapp_html()}
      <p>This is your e-ticket — show the QR code below at check-in for quick entry.</p>
      <p style="text-align:center; margin: 24px 0;">
        <img src="cid:ticket_qr" alt="Ticket QR code" width="220" height="220"><br>
        <span style="font-size:13px; color:#666;">Reference code: <strong>{code}</strong></span>
      </p>
      <p>We look forward to seeing you there.</p>
      {CONFIRMATION_FOOTER_HTML}
    """
    return send_email(
        email,
        f"You're confirmed! — {EVENT_NAME} e-ticket",
        html,
        {"ticket_qr": _ticket_qr_png_bytes(code)},
    )


def send_event_reminder_email(reg):
    name = esc(reg.get("name", ""))
    code = reg.get("ticket_code", "")
    email = reg["email"]
    html = f"""
      <p>Hi {name},</p>
      <p>Quick reminder — {esc(EVENT_NAME)} is tomorrow, {esc(EVENT_DATE)}, {esc(EVENT_TIME)}! We can't wait to
      see you.</p>
      <p><strong>📍 {esc(VENUE_NAME)}</strong><br>
      {esc(VENUE_ADDRESS)}{_directions_html()}</p>
      <p>Here's your e-ticket again — show the QR code below at check-in for quick entry.</p>
      <p style="text-align:center; margin: 24px 0;">
        <img src="cid:ticket_qr" alt="Ticket QR code" width="220" height="220"><br>
        <span style="font-size:13px; color:#666;">Reference code: <strong>{code}</strong></span>
      </p>
      <p>See you tomorrow!</p>
      {CONFIRMATION_FOOTER_HTML}
    """
    return send_email(
        email,
        f"Reminder: {EVENT_NAME} is tomorrow!",
        html,
        {"ticket_qr": _ticket_qr_png_bytes(code)},
    )


def send_invite_email(name, email, register_url, decline_url):
    intro_html = chapter_config.paragraphs_html(_CFG["content"]["invite_email"])
    html_body = f"""
      <p>Hi {esc(name)},</p>
      {intro_html}
      <p>📅 <strong>{esc(EVENT_DATE)}</strong>, {esc(EVENT_TIME)}<br>
      📍 <strong>{esc(VENUE_NAME)}</strong>, {esc(VENUE_ADDRESS)}</p>
      <p style="text-align:center; margin: 24px 0 10px;">
        <a href="{esc(register_url)}" style="display:inline-block; background:#7A2E2E; color:#fff;
           font-weight:600; font-size:15px; padding:12px 28px; border-radius:5px;
           text-decoration:none;">Yes, I'll be there →</a>
      </p>
      <p style="text-align:center; margin: 0 0 8px;">
        <a href="{esc(decline_url)}" style="display:inline-block; background:transparent; color:#7A2E2E;
           font-weight:600; font-size:13px; padding:9px 20px; border-radius:5px;
           border:1px solid #7A2E2E; text-decoration:none;">Can't make it this year?</a>
      </p>
      <p style="text-align:center; font-size:12px; color:#888; margin: 0 0 24px;">No hard feelings — just helps us plan.</p>
      {_whatsapp_html()}
      {INVITE_FOOTER_HTML}
    """
    return send_email(email, f"You're invited — {EVENT_NAME}, {EVENT_DATE_SHORT}", html_body)


def send_refund_confirmed_email(reg):
    name = esc(reg.get("name", ""))
    amount = f"${int(reg.get('amount_cents', 0)) / 100:.2f}"
    email = reg["email"]
    html = f"""
      <p>Hi {name},</p>
      <p>This confirms your registration for {esc(EVENT_NAME)} on {esc(EVENT_DATE)} has been cancelled, and
      your <strong>{amount}</strong> payment has been refunded via your original payment method.</p>
      <p>Change your mind? You're welcome to register again anytime before the event.</p>
      {CONFIRMATION_FOOTER_HTML}
    """
    return send_email(email, f"Refund confirmed — {EVENT_NAME}", html)
