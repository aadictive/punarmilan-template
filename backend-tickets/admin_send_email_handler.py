"""
Lambda: admin_send_email_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Admin-triggered emails to an already-paid attendee: either
         resending the e-ticket confirmation (e.g. they lost it, or the QR
         didn't render), or the "event is tomorrow" reminder. Both require
         "template" in the request body. Protected by X-Admin-Password.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  ADMIN_PASSWORD    - shared secret checked against the X-Admin-Password header
  ALLOWED_ORIGIN    - CORS origin to allow
  SENDER_EMAIL / GMAIL_APP_PASSWORD - Gmail SMTP sender (blank = skip sending)
"""
import json
import os

import boto3

from email_utils import send_event_reminder_email, send_registration_confirmed_email

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
table = dynamodb.Table(TABLE_NAME)

TEMPLATES = {
    "confirmation": send_registration_confirmed_email,
    "event_reminder": send_event_reminder_email,
}


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
    template_key = (body.get("template") or "").strip()
    if not email:
        return _response(400, {"error": "Missing email."})
    if template_key not in TEMPLATES:
        return _response(400, {"error": f"template must be one of: {', '.join(TEMPLATES)}"})

    resp = table.get_item(Key={"email": email})
    reg = resp.get("Item")
    if not reg:
        return _response(404, {"error": "No registration found for that email."})
    if reg.get("status") != "paid":
        return _response(400, {"error": "This registration isn't marked as paid yet."})

    send_fn = TEMPLATES[template_key]
    email_ok, email_err = send_fn(reg)
    response = {"ok": True}
    if not email_ok:
        response["email_warning"] = f"Could not send: {email_err}"
    return _response(200, response)
