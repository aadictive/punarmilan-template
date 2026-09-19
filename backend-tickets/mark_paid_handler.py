"""
Lambda: mark_paid_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Lets an admin manually mark a registration as paid, for the
         Venmo/Zelle path where payment happens outside the site and someone
         has to reconcile it by hand. Protected by X-Admin-Password.

         Sends the attendee a "you're confirmed" email once marked paid.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  ADMIN_PASSWORD    - shared secret checked against the X-Admin-Password header
  ALLOWED_ORIGIN    - CORS origin to allow
  SENDER_EMAIL      - From address verified in SES (blank = skip sending)
"""
import json
import os

import boto3
from botocore.exceptions import ClientError

from email_utils import send_registration_confirmed_email

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
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

    try:
        result = table.update_item(
            Key={"email": email},
            UpdateExpression="SET #s = :paid, payment_method = :method",
            ConditionExpression="attribute_exists(email)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":paid": "paid", ":method": "manual"},
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(404, {"error": "No registration found for that email."})
        print(f"DynamoDB error: {e}")
        return _response(500, {"error": "Something went wrong."})

    # Marking paid always succeeds even if the email fails - that's a real
    # payment confirmation, not something to undo over an email hiccup - but
    # tell the admin so they can follow up with the attendee directly.
    email_ok, email_err = send_registration_confirmed_email(result.get("Attributes", {}))
    response = {"ok": True}
    if not email_ok:
        print(f"Failed to send confirmation email: {email_err}")
        response["email_warning"] = f"Marked paid, but the confirmation email failed to send: {email_err}"

    return _response(200, response)
