"""
Lambda: send_instructions_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Sends the "how to pay via Venmo/Zelle" email as an explicit,
         confirmed step (a "Send payment instructions" button the attendee
         clicks), separate from just picking a radio button - so an email
         only goes out when they actually mean to finalize this step.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  ALLOWED_ORIGIN    - CORS origin to allow
  SENDER_EMAIL      - From address verified in SES (blank = skip sending)
  VENMO_HANDLE       - shown/QR'd in the payment-instructions email
  ZELLE_HANDLE       - shown/QR'd in the payment-instructions email
"""
import json
import os
from datetime import datetime, timezone

import boto3

from email_utils import send_payment_instructions_email

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
VENMO_HANDLE = os.environ.get("VENMO_HANDLE", "")
ZELLE_HANDLE = os.environ.get("ZELLE_HANDLE", "")
table = dynamodb.Table(TABLE_NAME)

ALLOWED_METHODS = {"venmo", "zelle"}


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

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    email = (body.get("email") or "").strip().lower()
    selected = (body.get("method") or "").strip().lower()
    if not email or selected not in ALLOWED_METHODS:
        return _response(400, {"error": "Invalid request."})

    resp = table.get_item(Key={"email": email})
    reg = resp.get("Item")
    if not reg:
        return _response(404, {"error": "No registration found for that email. Please register first."})
    if reg.get("status") == "paid":
        return _response(400, {"error": "This registration is already marked as paid."})

    ok, err = send_payment_instructions_email(reg, selected, VENMO_HANDLE, ZELLE_HANDLE)
    if not ok:
        print(f"Failed to send payment instructions email: {err}")
        if err and "not verified" in err.lower():
            # SES sandbox mode - can only send to pre-verified addresses until
            # production access is approved. Tell the truth instead of a fake "sent".
            return _response(503, {
                "error": "Email delivery isn't fully live yet (pending an Amazon approval) - "
                         "your registration is saved though. Please save your reference code "
                         f"({reg.get('ticket_code', '')}) and try again in a bit, or contact the organizer directly."
            })
        return _response(500, {"error": "Something went wrong sending the email. Please try again."})

    table.update_item(
        Key={"email": email},
        UpdateExpression="SET instructions_sent_at = :t",
        ExpressionAttributeValues={":t": datetime.now(timezone.utc).isoformat()},
    )

    return _response(200, {"ok": True})
