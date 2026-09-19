"""
Lambda: stripe_webhook_handler.py
Trigger: Lambda Function URL (POST) - called by Stripe, not by the frontend.
Purpose: v2 - Verifies the Stripe webhook signature and, on
         checkout.session.completed, marks the matching registration as paid.

Setup (once you have a real Stripe account):
  1. Deploy this stack, note the WebhookEndpoint output.
  2. In the Stripe Dashboard -> Developers -> Webhooks, add that URL as an
     endpoint listening for "checkout.session.completed".
  3. Copy the signing secret Stripe gives you into the StripeWebhookSecret
     parameter and redeploy.

         Sends the attendee a "you're confirmed" email directly - card payers
         skip the "please pay" step since Stripe checkout itself is that step.

Env vars required:
  TABLE_NAME             - DynamoDB table name (e.g. "AlumniTickets")
  STRIPE_WEBHOOK_SECRET   - signing secret from the Stripe webhook dashboard
  SENDER_EMAIL            - From address verified in SES (blank = skip sending)
"""
import base64
import json
import os

import boto3

from email_utils import send_registration_confirmed_email

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "AlumniTickets")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
table = dynamodb.Table(TABLE_NAME)


def _response(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def handler(event, context):
    if not STRIPE_WEBHOOK_SECRET:
        # Not configured yet - fail loudly in logs but don't error Stripe's retries into a storm.
        print("STRIPE_WEBHOOK_SECRET not set - ignoring webhook call.")
        return _response(200, {"ignored": True})

    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body)
    else:
        raw_body = raw_body.encode("utf-8")

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("stripe-signature", "")

    import stripe
    try:
        stripe_event = stripe.Webhook.construct_event(raw_body, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        print(f"Webhook signature verification failed: {e}")
        return _response(400, {"error": "Invalid signature"})

    if stripe_event["type"] == "checkout.session.completed":
        session = stripe_event["data"]["object"]
        email = (session.get("customer_email") or session.get("metadata", {}).get("email") or "").strip().lower()
        if email:
            result = table.update_item(
                Key={"email": email},
                UpdateExpression="SET #s = :paid, payment_method = :method, stripe_payment_intent = :pi",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":paid": "paid",
                    ":method": "stripe",
                    ":pi": session.get("payment_intent", ""),
                },
                ReturnValues="ALL_NEW",
            )
            email_ok, email_err = send_registration_confirmed_email(result.get("Attributes", {}))
            if not email_ok:
                print(f"Failed to send confirmation email for {email}: {email_err}")

    return _response(200, {"received": True})
