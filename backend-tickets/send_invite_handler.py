"""
Lambda: send_invite_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Admin-triggered invite email: sends a personalized "Yes, I'll
         be there" link (pre-fills the registration form with their name and
         email) and a "Can't make it" link (one-click decline landing page).
         Designed to be called once per alumnus from a paced mail-merge
         Apps Script over the full alumni list - doesn't touch DynamoDB
         itself, no record is created until the recipient actually acts on
         one of the two links. Protected by X-Admin-Password.

Env vars required:
  ADMIN_PASSWORD    - shared secret checked against the X-Admin-Password header
  ALLOWED_ORIGIN    - CORS origin to allow
  SUCCESS_URL        - reused just for its origin (e.g. https://xxx.cloudfront.net/?paid=1)
                        to build the register/decline links - same env var
                        CheckoutFunction already uses, no new parameter needed
  SENDER_EMAIL / GMAIL_APP_PASSWORD - Gmail SMTP sender (blank = skip sending)
"""
import json
import os
from urllib.parse import quote

from email_utils import send_invite_email

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
SUCCESS_URL = os.environ.get("SUCCESS_URL", "https://example.com/success")


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

    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    if not name or not email:
        return _response(400, {"error": "Missing name or email."})

    site_url = SUCCESS_URL.split("?")[0].rstrip("/")
    qs = f"name={quote(name)}&email={quote(email)}"
    register_url = f"{site_url}/?{qs}"
    decline_url = f"{site_url}/decline?{qs}"

    email_ok, email_err = send_invite_email(name, email, register_url, decline_url)
    response = {"ok": True}
    if not email_ok:
        response["email_warning"] = f"Invite could not be sent: {email_err}"
    return _response(200, response)
