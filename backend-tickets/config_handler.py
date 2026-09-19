"""
Lambda: config_handler.py
Trigger: Lambda Function URL (GET)
Purpose: v2 - Public, unauthenticated config the frontend reads at load time so
         price / payment method availability can change (via redeploy with new
         parameter overrides) without a frontend rebuild.

Env vars required:
  ALLOWED_ORIGIN       - CORS origin to allow
  TICKET_PRICE_CENTS   - price per ticket, in cents
  STRIPE_SECRET_KEY    - presence (not value) is exposed as stripe_enabled
  VENMO_HANDLE          - e.g. "@your-chapter-venmo" (empty string if not set up yet)
  ZELLE_HANDLE          - e.g. an email or phone number (empty string if not set up yet)
"""
import json
import os

from fees import card_price_cents

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
TICKET_PRICE_CENTS = int(os.environ.get("TICKET_PRICE_CENTS", "6500"))
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
VENMO_HANDLE = os.environ.get("VENMO_HANDLE", "")
ZELLE_HANDLE = os.environ.get("ZELLE_HANDLE", "")


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }


def _response(status, body):
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    return _response(200, {
        "ticket_price_cents": TICKET_PRICE_CENTS,
        "card_price_cents": card_price_cents(TICKET_PRICE_CENTS),
        "stripe_enabled": bool(STRIPE_SECRET_KEY),
        "venmo_handle": VENMO_HANDLE,
        "zelle_handle": ZELLE_HANDLE,
        "manual_payment_enabled": bool(VENMO_HANDLE or ZELLE_HANDLE),
    })
