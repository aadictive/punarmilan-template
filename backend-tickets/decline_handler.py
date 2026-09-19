"""
Lambda: decline_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Public endpoint for the "can't make it" decline flow, called
         from the /decline landing page after someone confirms via their
         personalized invite link. Writes a lightweight status: "declined"
         record - no batch/college/phone required, unlike a real
         registration. Won't silently overwrite an existing paid
         registration (in case someone clicks an old invite link after
         already registering separately) - reports "already_registered"
         instead. Refund history, if any, is carried forward the same way
         register_handler.py does, so it isn't lost.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  ALLOWED_ORIGIN    - CORS origin to allow
"""
import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
table = dynamodb.Table(TABLE_NAME)


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
    name = (body.get("name") or "").strip()
    if not email:
        return _response(400, {"error": "Missing email."})

    existing = table.get_item(Key={"email": email}).get("Item") or {}

    # Carry forward refund history the same way register_handler.py does,
    # so declining afterwards doesn't erase it.
    if existing.get("status") == "refunded":
        previously_refunded_at = existing.get("refunded_at")
        previously_refunded_ticket_code = existing.get("ticket_code")
    else:
        previously_refunded_at = existing.get("previously_refunded_at")
        previously_refunded_ticket_code = existing.get("previously_refunded_ticket_code")
    refund_count = existing.get("refund_count") or 0

    item = {
        "email": email,
        "name": name or existing.get("name", ""),
        "status": "declined",
        "declined_at": datetime.now(timezone.utc).isoformat(),
        "created_at": existing.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    if previously_refunded_at:
        item["previously_refunded_at"] = previously_refunded_at
    if previously_refunded_ticket_code:
        item["previously_refunded_ticket_code"] = previously_refunded_ticket_code
    if refund_count:
        item["refund_count"] = refund_count

    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(email) OR #s <> :paid",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":paid": "paid"},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(200, {"ok": True, "already_registered": True})
        print(f"DynamoDB error: {e}")
        return _response(500, {"error": "Something went wrong. Please try again."})

    return _response(200, {"ok": True})
