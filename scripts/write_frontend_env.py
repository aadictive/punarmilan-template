#!/usr/bin/env python3
"""
write_frontend_env.py - after `sam deploy`, turn the stack's outputs into
frontend-tickets/.env.production so the website knows which backend URLs to call.

Usage: python3 scripts/write_frontend_env.py <stack-name> [region]
Needs the AWS CLI (already required for deploying).
"""
import json
import os
import subprocess
import sys

OUTPUT_TO_ENV = {
    "RegisterEndpoint": "VITE_REGISTER_ENDPOINT",
    "ConfigEndpoint": "VITE_CONFIG_ENDPOINT",
    "CheckoutEndpoint": "VITE_CHECKOUT_ENDPOINT",
    "AdminEndpoint": "VITE_ADMIN_ENDPOINT",
    "MarkPaidEndpoint": "VITE_MARK_PAID_ENDPOINT",
    "UnmarkPaidEndpoint": "VITE_UNMARK_PAID_ENDPOINT",
    "SelectMethodEndpoint": "VITE_SELECT_METHOD_ENDPOINT",
    "SendInstructionsEndpoint": "VITE_SEND_INSTRUCTIONS_ENDPOINT",
    "SendReminderEndpoint": "VITE_SEND_REMINDER_ENDPOINT",
    "TrackViewEndpoint": "VITE_TRACK_VIEW_ENDPOINT",
    "CheckinEndpoint": "VITE_CHECKIN_ENDPOINT",
    "AdminCheckinEndpoint": "VITE_ADMIN_CHECKIN_ENDPOINT",
    "AdminSendEmailEndpoint": "VITE_ADMIN_SEND_EMAIL_ENDPOINT",
    "DeclineEndpoint": "VITE_DECLINE_ENDPOINT",
}


def stack_outputs(stack, region):
    cmd = ["aws", "cloudformation", "describe-stacks", "--stack-name", stack, "--query", "Stacks[0].Outputs", "--output", "json"]
    if region:
        cmd += ["--region", region]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return {o["OutputKey"]: o["OutputValue"] for o in json.loads(out)}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    stack = sys.argv[1]
    region = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("AWS_REGION", "")
    outputs = stack_outputs(stack, region)
    missing = [k for k in OUTPUT_TO_ENV if k not in outputs]
    if missing:
        sys.exit(f"Stack {stack} is missing expected outputs: {', '.join(missing)}")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(root, "frontend-tickets", ".env.production")
    with open(path, "w") as f:
        for key, env_name in OUTPUT_TO_ENV.items():
            f.write(f"{env_name}={outputs[key]}\n")
    print(f"wrote {os.path.relpath(path, root)} ({len(OUTPUT_TO_ENV)} endpoints)")


if __name__ == "__main__":
    main()
