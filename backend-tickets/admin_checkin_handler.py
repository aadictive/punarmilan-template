"""
Lambda: admin_checkin_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Lets an admin manually set or undo a check-in from the admin
         panel (distinct from checkin_handler.py, which is what door
         volunteers use via the link-authenticated /checkin page). Useful for
         fixing a mistaken scan, or checking someone in by hand if the QR
         scan fails at the door. Protected by X-Admin-Password.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  ADMIN_PASSWORD    - shared secret checked against the X-Admin-Password header
  ALLOWED_ORIGIN    - CORS origin to allow
"""
import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

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
    checked_in = bool(body.get("checked_in"))

    try:
        if checked_in:
            table.update_item(
                Key={"email": email},
                UpdateExpression="SET checked_in = :true, checked_in_at = :now",
                ConditionExpression="attribute_exists(email)",
                ExpressionAttributeValues={":true": True, ":now": datetime.now(timezone.utc).isoformat()},
            )
        else:
            table.update_item(
                Key={"email": email},
                UpdateExpression="SET checked_in = :false REMOVE checked_in_at",
                ConditionExpression="attribute_exists(email)",
                ExpressionAttributeValues={":false": False},
            )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(404, {"error": "No registration found for that email."})
        print(f"DynamoDB error: {e}")
        return _response(500, {"error": "Something went wrong."})

    return _response(200, {"ok": True})
