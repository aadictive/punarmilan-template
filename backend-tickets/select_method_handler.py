"""
Lambda: select_method_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Records which payment method an attendee picked (Venmo / Zelle /
         card) on the payment screen, *before* payment is actually confirmed.
         This is separate from `payment_method`, which only gets set once a
         payment is actually confirmed (by the Stripe webhook or an admin's
         "Mark paid" click) - `selected_payment_method` lets the organizer see
         intent for reconciliation ("they said Venmo, let me check Venmo for
         their reference code") even while status is still pending_payment.

         Does NOT send any email itself - that's a separate explicit step
         (see send_instructions_handler.py), triggered by a "Send payment
         instructions" button, so picking a radio button alone never fires
         an email.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  ALLOWED_ORIGIN    - CORS origin to allow
"""
import json
import os

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
table = dynamodb.Table(TABLE_NAME)

ALLOWED_METHODS = {"venmo", "zelle", "card"}


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

    try:
        table.update_item(
            Key={"email": email},
            UpdateExpression="SET selected_payment_method = :m",
            ConditionExpression="attribute_exists(email)",
            ExpressionAttributeValues={":m": selected},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(404, {"error": "No registration found for that email."})
        print(f"DynamoDB error: {e}")
        return _response(500, {"error": "Something went wrong."})

    return _response(200, {"ok": True})
