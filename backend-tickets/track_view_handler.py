"""
Lambda: track_view_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Records that someone reached the "confirm your email + see the
         price" screen, before they've actually confirmed registration.
         Written with status "viewed_price" - if they go on to confirm,
         register_handler.py overwrites this same record (same email/partition
         key) with status "pending_payment". If they never confirm, the record
         just stays at "viewed_price" forever, which is the drop-off signal:
         count(status=viewed_price) among those who never advanced tells the
         organizer how many people saw the price and didn't continue.

Env vars required:
  TABLE_NAME          - DynamoDB table name (e.g. "AlumniTickets")
  ALLOWED_ORIGIN       - CORS origin to allow
  TICKET_PRICE_CENTS   - price per ticket, in cents
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
TICKET_PRICE_CENTS = int(os.environ.get("TICKET_PRICE_CENTS", "6500"))
table = dynamodb.Table(TABLE_NAME)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EXPECTATIONS = 10


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
    if not email or not EMAIL_RE.match(email) or not name:
        return _response(400, {"error": "Invalid request."})

    # Don't clobber a registration that's already further along than this -
    # including refunded/declined, which carry real history (refund_count,
    # previously_refunded_at, etc.) that a bare put_item here would silently
    # wipe before register_handler.py ever gets a chance to carry it forward.
    existing = table.get_item(Key={"email": email}).get("Item")
    if existing and existing.get("status") in ("pending_payment", "paid", "refunded", "declined"):
        return _response(200, {"ok": True})

    expectations = body.get("expectations") or []
    if not isinstance(expectations, list):
        expectations = []
    expectations = [str(e).strip()[:100] for e in expectations if str(e).strip()][:MAX_EXPECTATIONS]

    item = {
        "email": email,
        "ticket_id": str(uuid.uuid4()),
        "ticket_code": str(uuid.uuid4())[:8].upper(),
        "name": name,
        "phone": (body.get("phone") or "").strip(),
        "batch": (body.get("batch") or "").strip(),
        "college": (body.get("college") or "").strip(),
        "linkedin": (body.get("linkedin") or "").strip(),
        "quantity": 1,
        "unit_price_cents": TICKET_PRICE_CENTS,
        "amount_cents": TICKET_PRICE_CENTS,
        "volunteer": bool(body.get("volunteer")),
        "expectations": expectations,
        "status": "viewed_price",
        "payment_method": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    table.put_item(Item=item)
    return _response(200, {"ok": True})
