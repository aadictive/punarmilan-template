"""
Lambda: send_payment_reminder_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Admin-triggered nudge for a registration that's still
         pending_payment. Leads with whichever payment method the attendee
         actually selected (Venmo/Zelle QR + instructions, or a card link),
         with the other method offered as a secondary option - not a card
         link for everyone regardless of what they picked. Protected by
         X-Admin-Password.

Env vars required:
  TABLE_NAME             - DynamoDB table name (e.g. "AlumniTickets")
  ADMIN_PASSWORD          - shared secret checked against the X-Admin-Password header
  ALLOWED_ORIGIN          - CORS origin to allow
  STRIPE_SECRET_KEY       - Stripe secret key. If unset, the reminder still
                             sends, just without a card-payment link.
  SUCCESS_URL / CANCEL_URL - same as CheckoutFunction
  VENMO_HANDLE / ZELLE_HANDLE - same as ConfigFunction
  SENDER_EMAIL / GMAIL_APP_PASSWORD - Gmail SMTP sender (blank = skip sending)
"""
import json
import os

import boto3

from email_utils import send_payment_reminder_email
import chapter_config
from fees import card_price_cents

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
SUCCESS_URL = os.environ.get("SUCCESS_URL", "https://example.com/success")
CANCEL_URL = os.environ.get("CANCEL_URL", "https://example.com/cancel")
VENMO_HANDLE = os.environ.get("VENMO_HANDLE", "")
ZELLE_HANDLE = os.environ.get("ZELLE_HANDLE", "")
table = dynamodb.Table(TABLE_NAME)
EVENT_NAME = chapter_config.get()["event"]["name"]


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Admin-Password",
        "Content-Type": "application/json",
    }


def _response(status, body):
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not ADMIN_PASSWORD or headers.get("x-admin-password", "") != ADMIN_PASSWORD:
        return _response(401, {"error": "Unauthorized"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    email = (body.get("email") or "").strip().lower()
    if not email:
        return _response(400, {"error": "Missing email."})

    resp = table.get_item(Key={"email": email})
    reg = resp.get("Item")
    if not reg:
        return _response(404, {"error": "No registration found for that email."})
    if reg.get("status") == "paid":
        return _response(400, {"error": "This registration is already marked as paid."})

    checkout_url = None
    card_amount_cents = None
    if STRIPE_SECRET_KEY:
        import stripe  # imported here so the rest of the handler still works even
                        # before `pip install stripe` has been run for this function
        stripe.api_key = STRIPE_SECRET_KEY
        stripe.default_http_client = stripe.http_client.RequestsClient(timeout=8)

        ticket_code = reg.get("ticket_code", "")
        card_amount_cents = card_price_cents(int(reg["unit_price_cents"]))
        success_url = SUCCESS_URL + ("&" if "?" in SUCCESS_URL else "?") + "session_id={CHECKOUT_SESSION_ID}"
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": f"{EVENT_NAME} — Ticket ({ticket_code})"},
                        "unit_amount": card_amount_cents,
                    },
                    "quantity": 1,
                }],
                customer_email=email,
                client_reference_id=reg.get("ticket_id", ""),
                success_url=success_url,
                cancel_url=CANCEL_URL,
                metadata={"email": email, "ticket_id": reg.get("ticket_id", ""), "ticket_code": ticket_code},
                payment_intent_data={
                    "description": f"{EVENT_NAME} — Ticket {ticket_code}",
                    "metadata": {"ticket_code": ticket_code, "email": email},
                },
            )
            checkout_url = session.url
            table.update_item(
                Key={"email": email},
                UpdateExpression="SET stripe_session_id = :sid",
                ExpressionAttributeValues={":sid": session.id},
            )
        except Exception as e:
            # Don't fail the whole reminder over a Stripe hiccup - just send
            # the email without a card link this time.
            print(f"Stripe error creating reminder checkout session for {email}: {type(e).__name__}: {e}")
            checkout_url = None

    site_url = SUCCESS_URL.split("?")[0]
    email_ok, email_err = send_payment_reminder_email(
        reg, checkout_url, card_amount_cents, site_url, VENMO_HANDLE, ZELLE_HANDLE
    )
    response = {"ok": True}
    if not email_ok:
        response["email_warning"] = f"Reminder could not be sent: {email_err}"
    return _response(200, response)
