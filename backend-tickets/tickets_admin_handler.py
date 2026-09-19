"""
Lambda: tickets_admin_handler.py
Trigger: Lambda Function URL (GET)
Purpose: v2 - Returns all ticket registrations for the admin page. Accepts
         either the full-admin password or the view-only password in the
         X-Admin-Password header - both can read here. The distinction that
         actually matters is enforced elsewhere: mark_paid_handler.py,
         unmark_paid_handler.py, send_payment_reminder_handler.py and
         admin_checkin_handler.py only accept ADMIN_PASSWORD, so a view-only
         login simply can't authenticate any mutating action, regardless of
         what the frontend shows. Supports ?format=csv for a raw CSV download.

Env vars required:
  TABLE_NAME           - DynamoDB table name (e.g. "AlumniTickets")
  ADMIN_PASSWORD        - full-access shared secret
  VIEW_ONLY_PASSWORD    - read-only shared secret (leave blank to disable
                           view-only login entirely)
  ALLOWED_ORIGIN        - CORS origin to allow
"""
import csv
import hmac
import io
import json
import os
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
VIEW_ONLY_PASSWORD = os.environ.get("VIEW_ONLY_PASSWORD", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
table = dynamodb.Table(TABLE_NAME)

CSV_FIELDS = [
    "name", "email", "phone", "batch", "college", "linkedin",
    "quantity", "amount_cents", "status", "payment_method", "selected_payment_method",
    "ticket_code", "checked_in", "checked_in_at", "volunteer", "expectations", "created_at",
    "refund_count", "previously_refunded_at", "previously_refunded_ticket_code",
    "declined_at", "previously_declined_at",
]


def _csv_row(item):
    row = dict(item)
    row["volunteer"] = "Yes" if row.get("volunteer") else "No"
    row["checked_in"] = "Yes" if row.get("checked_in") else "No"
    row["expectations"] = "; ".join(row.get("expectations") or [])
    if row.get("phone"):
        row["phone"] = f"{row.get('country_code') or '+1'} {row['phone']}"
    return row


def _json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def _cors_headers(content_type="application/json"):
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Admin-Password",
        "Content-Type": content_type,
    }


def _response(status, body, content_type="application/json"):
    return {
        "statusCode": status,
        "headers": _cors_headers(content_type),
        "body": body if content_type != "application/json" else json.dumps(body, default=_json_default),
    }


def _get_all_items():
    items = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    supplied_password = headers.get("x-admin-password", "")

    # Tell the admin page which login this was, so it can enable/disable its
    # buttons without hardcoding anyone's password in the frontend. (Every
    # mutating endpoint still checks ADMIN_PASSWORD itself - this only
    # controls what the page shows.)
    role = None
    if ADMIN_PASSWORD and hmac.compare_digest(supplied_password.encode(), ADMIN_PASSWORD.encode()):
        role = "admin"
    elif VIEW_ONLY_PASSWORD and hmac.compare_digest(supplied_password.encode(), VIEW_ONLY_PASSWORD.encode()):
        role = "view_only"
    if role is None:
        return _response(401, {"error": "Unauthorized"})

    query_params = event.get("queryStringParameters") or {}
    items = _get_all_items()

    if query_params.get("format") == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            writer.writerow(_csv_row(item))
        csv_body = buf.getvalue()
        resp = _response(200, csv_body, content_type="text/csv")
        resp["headers"]["Content-Disposition"] = 'attachment; filename="tickets.csv"'
        return resp

    paid_count = sum(1 for i in items if i.get("status") == "paid")
    total_collected_cents = sum(int(i.get("amount_cents", 0)) for i in items if i.get("status") == "paid")
    checked_in_count = sum(1 for i in items if i.get("checked_in"))
    refunded_count = sum(1 for i in items if i.get("status") == "refunded")
    declined_count = sum(1 for i in items if i.get("status") == "declined")
    return _response(200, {
        "role": role,
        "count": len(items),
        "paid_count": paid_count,
        "refunded_count": refunded_count,
        "declined_count": declined_count,
        "total_collected_cents": total_collected_cents,
        "checked_in_count": checked_in_count,
        "items": items,
    })
