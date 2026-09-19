"""
Lambda: checkin_handler.py
Trigger: Lambda Function URL (POST)
Purpose: v2 - Day-of-event door check-in. A volunteer's phone scans (or
         manually types) the code from an attendee's e-ticket QR; this looks
         up the matching registration, marks it checked in, and returns
         enough info for the volunteer to see at a glance whether it's a
         valid, paid, not-yet-checked-in attendee.

         Auth: not the admin password - a single shared CHECKIN_KEY baked
         into the check-in page's URL (?key=...), so volunteers just open a
         link on their own phones rather than typing a password at the door.
         Not as strong as a real login, but keeps the door flow to "open link,
         start scanning" across as many devices as needed on the day.

Env vars required:
  TABLE_NAME       - DynamoDB table name (e.g. "AlumniTickets")
  CHECKIN_KEY       - shared secret that must be sent in the request body
  ALLOWED_ORIGIN    - CORS origin to allow
"""
import json
import os
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
CHECKIN_KEY = os.environ.get("CHECKIN_KEY", "")
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


def _find_by_code(code):
    # ticket_code isn't the partition key (email is), so this is a scan - at
    # this event's scale (~150-200 attendees) that's cheap and fast enough
    # for a door check-in flow with no added infra (a GSI would be overkill).
    resp = table.scan(FilterExpression=Attr("ticket_code").eq(code))
    items = resp.get("Items", [])
    return items[0] if items else None


def _checked_in_count():
    resp = table.scan(FilterExpression=Attr("checked_in").eq(True), Select="COUNT")
    return resp.get("Count", 0)


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    if not CHECKIN_KEY or body.get("key") != CHECKIN_KEY:
        return _response(401, {"error": "Unauthorized"})

    raw_code = (body.get("code") or "").strip().upper()
    if not raw_code:
        return _response(400, {"error": "Missing code."})
    # The e-ticket QR encodes "PUNARMILAN-TICKET:XXXXXXXX" - accept either that
    # full scanned string or just the bare 8-character code (manual entry).
    code = raw_code.split(":")[-1].strip()

    item = _find_by_code(code)
    if not item:
        return _response(404, {"error": "No ticket found with that code."})

    already_checked_in = bool(item.get("checked_in"))
    if not already_checked_in:
        now = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={"email": item["email"]},
            UpdateExpression="SET checked_in = :true, checked_in_at = :now",
            ExpressionAttributeValues={":true": True, ":now": now},
        )
        item["checked_in_at"] = now

    return _response(200, {
        "ok": True,
        "name": item.get("name", ""),
        "batch": item.get("batch", ""),
        "college": item.get("college", ""),
        "status": item.get("status", ""),
        "already_checked_in": already_checked_in,
        "checked_in_at": item.get("checked_in_at", ""),
        "checked_in_count": _checked_in_count(),
    })
