"""
Lambda: unmark_paid_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Lets an admin undo a "Mark paid" click, either because it was a
         mistake (reverts to "pending_payment", clearing payment_method - the
         original behavior, no email sent) or because the attendee cancelled
         and was refunded (sets "refunded", keeps payment_method as a record
         of how they'd originally paid, and emails a refund confirmation).
         Which one is controlled by the optional "target_status" field in the
         request body - defaults to "pending_payment" for backward
         compatibility. Protected by X-Admin-Password. The refund email is
         just a record for the attendee - the actual money movement (Stripe
         Dashboard / Venmo / Zelle) is still a manual step the admin does
         themselves, separate from this call.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  ADMIN_PASSWORD    - shared secret checked against the X-Admin-Password header
  ALLOWED_ORIGIN    - CORS origin to allow
  SENDER_EMAIL / GMAIL_APP_PASSWORD - Gmail SMTP sender (blank = skip sending)
"""
import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from email_utils import send_refund_confirmed_email

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
ALLOWED_TARGET_STATUSES = {"pending_payment", "refunded"}
table = dynamodb.Table(TABLE_NAME)


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

    target_status = (body.get("target_status") or "pending_payment").strip()
    if target_status not in ALLOWED_TARGET_STATUSES:
        return _response(400, {"error": "Invalid target_status."})

    try:
        if target_status == "refunded":
            # Keep payment_method as-is - it's a useful record of how they
            # originally paid, unlike the "clicked the wrong row" case below.
            result = table.update_item(
                Key={"email": email},
                UpdateExpression=(
                    "SET #s = :refunded, refunded_at = :now, "
                    "refund_count = if_not_exists(refund_count, :zero) + :one"
                ),
                ConditionExpression="attribute_exists(email)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":refunded": "refunded",
                    ":now": datetime.now(timezone.utc).isoformat(),
                    ":zero": 0,
                    ":one": 1,
                },
                ReturnValues="ALL_NEW",
            )
        else:
            result = None
            table.update_item(
                Key={"email": email},
                UpdateExpression="SET #s = :pending, payment_method = :method",
                ConditionExpression="attribute_exists(email)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":pending": "pending_payment", ":method": ""},
            )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(404, {"error": "No registration found for that email."})
        print(f"DynamoDB error: {e}")
        return _response(500, {"error": "Something went wrong."})

    response = {"ok": True}
    if target_status == "refunded":
        email_ok, email_err = send_refund_confirmed_email(result.get("Attributes", {}))
        if not email_ok:
            print(f"Failed to send refund confirmation email: {email_err}")
            response["email_warning"] = f"Marked refunded, but the confirmation email failed to send: {email_err}"

    return _response(200, response)
