"""
Lambda: register_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Accepts a ticket registration and writes it to DynamoDB with
         status "pending_payment". Amount is snapshotted at registration time
         from TICKET_PRICE_CENTS so later price changes don't affect existing
         registrations.

Env vars required:
  TABLE_NAME          - DynamoDB table name (e.g. "AlumniTickets")
  ALLOWED_ORIGIN       - CORS origin to allow
  TICKET_PRICE_CENTS   - price per ticket, in cents (e.g. 5000 = $50.00)
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
TICKET_PRICE_CENTS = int(os.environ.get("TICKET_PRICE_CENTS", "6500"))
table = dynamodb.Table(TABLE_NAME)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\d{10}$")
ALLOWED_COUNTRY_CODES = {"+1", "+91"}
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

    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    country_code = (body.get("countryCode") or "+1").strip()
    if country_code not in ALLOWED_COUNTRY_CODES:
        country_code = "+1"
    phone = re.sub(r"\D", "", body.get("phone") or "")
    batch = (body.get("batch") or "").strip()
    college = (body.get("college") or "").strip()
    linkedin = (body.get("linkedin") or "").strip()
    volunteer = bool(body.get("volunteer"))
    expectations = body.get("expectations") or []

    if not name or len(name) > 200:
        return _response(400, {"error": "Please provide a valid name."})
    if not email or not EMAIL_RE.match(email):
        return _response(400, {"error": "Please provide a valid email."})
    if not PHONE_RE.match(phone):
        return _response(400, {"error": "Please provide a valid 10-digit phone number."})
    if not batch or len(batch) > 50:
        return _response(400, {"error": "Please provide your batch / graduation year."})
    if not college or len(college) > 200:
        return _response(400, {"error": "Please provide your college / institution."})
    if not isinstance(expectations, list) or len(expectations) > MAX_EXPECTATIONS:
        return _response(400, {"error": "Invalid expectations selection."})
    expectations = [str(e).strip()[:100] for e in expectations if str(e).strip()]

    quantity = 1  # one registration per attendee - no group/bulk tickets
    amount_cents = quantity * TICKET_PRICE_CENTS

    # Read the existing record (if any) before overwriting it, so the response
    # can tell the frontend "you already picked Venmo last time" - resubmitting
    # the form (e.g. to switch payment methods) shouldn't silently erase that.
    existing = table.get_item(Key={"email": email}).get("Item") or {}
    prior_selected_payment_method = existing.get("selected_payment_method") or ""

    # Likewise, if the prior record for this email was refunded, that history
    # would otherwise vanish the moment they register again (a fresh put_item
    # overwrites it entirely) - carry it forward instead. If the existing
    # record IS the refund itself, pull from it directly; otherwise it may
    # already be carrying history forward from an even earlier cycle, so just
    # keep passing that along.
    if existing.get("status") == "refunded":
        previously_refunded_at = existing.get("refunded_at")
        previously_refunded_ticket_code = existing.get("ticket_code")
    else:
        previously_refunded_at = existing.get("previously_refunded_at")
        previously_refunded_ticket_code = existing.get("previously_refunded_ticket_code")
    refund_count = existing.get("refund_count") or 0

    # Same idea for a prior decline - registering after saying "can't make it"
    # should be seamless (that's the whole point of the decline email saying
    # "if you change your mind..."), but the fact they once declined is still
    # worth keeping around rather than silently dropping.
    if existing.get("status") == "declined":
        previously_declined_at = existing.get("declined_at")
    else:
        previously_declined_at = existing.get("previously_declined_at")

    item = {
        "email": email,  # partition key - one registration per email, resubmission updates it
        "ticket_id": str(uuid.uuid4()),
        "ticket_code": str(uuid.uuid4())[:8].upper(),  # short reference for manual payment memo
        "name": name,
        "country_code": country_code,
        "phone": phone,
        "batch": batch,
        "college": college,
        "linkedin": linkedin,
        "quantity": quantity,
        "unit_price_cents": TICKET_PRICE_CENTS,
        "amount_cents": amount_cents,
        "volunteer": volunteer,
        "expectations": expectations,
        "status": "pending_payment",
        "payment_method": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if previously_refunded_at:
        item["previously_refunded_at"] = previously_refunded_at
    if previously_refunded_ticket_code:
        item["previously_refunded_ticket_code"] = previously_refunded_ticket_code
    if refund_count:
        item["refund_count"] = refund_count
    if previously_declined_at:
        item["previously_declined_at"] = previously_declined_at

    try:
        # Email is the partition key, so resubmitting the same email normally
        # just overwrites the prior record (e.g. someone switching payment
        # method retries registration) - that's fine. But if that prior
        # record is already paid, silently overwriting it would erase a
        # confirmed registration, so block that specific case instead.
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(email) OR #s <> :paid",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":paid": "paid"},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _response(409, {
                "error": "This email is already registered and paid for. If you're registering "
                         "another attendee, please use a different email address. If this is a "
                         "mistake, contact the organizer."
            })
        print(f"DynamoDB error: {e}")
        return _response(500, {"error": "Something went wrong saving your registration. Please try again."})

    return _response(200, {
        "ok": True,
        "email": email,
        "ticket_code": item["ticket_code"],
        "quantity": quantity,
        "amount_cents": amount_cents,
        "prior_selected_payment_method": prior_selected_payment_method,
    })
