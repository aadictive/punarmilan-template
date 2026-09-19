"""
Lambda: create_checkout_session_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Creates a Stripe Checkout Session for an existing registration
         and returns the hosted checkout URL to redirect the browser to.

         Gracefully returns 503 if STRIPE_SECRET_KEY isn't configured yet, so
         the "Pay by card" button can be disabled/hidden client-side (via
         config_handler's stripe_enabled flag) without this ever erroring for
         real attendees.

Env vars required:
  TABLE_NAME          - DynamoDB table name (e.g. "AlumniTickets")
  ALLOWED_ORIGIN       - CORS origin to allow
  STRIPE_SECRET_KEY    - Stripe secret key (sk_live_... / sk_test_...). Leave
                          unset until you have a real Stripe account.
  SUCCESS_URL           - full URL Stripe redirects to after a successful payment
  CANCEL_URL             - full URL Stripe redirects to if the attendee cancels
"""
import json
import os

import boto3

import chapter_config
from fees import card_price_cents

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
SUCCESS_URL = os.environ.get("SUCCESS_URL", "https://example.com/success")
CANCEL_URL = os.environ.get("CANCEL_URL", "https://example.com/cancel")
table = dynamodb.Table(TABLE_NAME)
EVENT_NAME = chapter_config.get()["event"]["name"]


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }


def _response(status, body):
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    if not STRIPE_SECRET_KEY:
        return _response(503, {"error": "Card payments aren't set up yet. Please use the Venmo/Zelle option, or check back soon."})

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
        return _response(404, {"error": "No registration found for that email. Please register first."})
    if reg.get("status") == "paid":
        return _response(400, {"error": "This registration is already marked as paid."})

    import stripe  # imported here so the rest of the handler still works (and returns a clean
                    # 503 above) even before `pip install stripe` has been run for this function
    stripe.api_key = STRIPE_SECRET_KEY
    stripe.default_http_client = stripe.http_client.RequestsClient(timeout=8)

    ticket_code = reg.get("ticket_code", "")
    # Gross up so the org still nets the full ticket price - the card payer
    # absorbs Stripe's processing fee, not us.
    charge_cents = card_price_cents(int(reg["unit_price_cents"]))
    success_url = SUCCESS_URL + ("&" if "?" in SUCCESS_URL else "?") + "session_id={CHECKOUT_SESSION_ID}"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"{EVENT_NAME} — Ticket ({ticket_code})"},
                    "unit_amount": charge_cents,
                },
                "quantity": 1,
            }],
            customer_email=email,
            client_reference_id=reg["ticket_id"],
            success_url=success_url,
            cancel_url=CANCEL_URL,
            metadata={"email": email, "ticket_id": reg["ticket_id"], "ticket_code": ticket_code},
            payment_intent_data={
                "description": f"{EVENT_NAME} — Ticket {ticket_code}",
                "metadata": {"ticket_code": ticket_code, "email": email},
            },
        )
    except Exception as e:
        print(f"Stripe error: {type(e).__name__}: {e}")
        return _response(502, {"error": "Something went wrong starting checkout. Please try again."})

    table.update_item(
        Key={"email": email},
        UpdateExpression="SET stripe_session_id = :sid",
        ExpressionAttributeValues={":sid": session.id},
    )

    return _response(200, {"url": session.url})
