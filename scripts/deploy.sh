#!/usr/bin/env bash
# =============================================================================
# deploy.sh - build and deploy this chapter's whole site (backend + website).
#
# The GitHub Action runs this for you on every push, so most people never run
# it by hand. To run it yourself you need: AWS CLI + SAM CLI + Node 18+ +
# Python 3.12 with `pip install pyyaml`, AWS credentials for your stack, and
# the secrets below exported as environment variables.
#
# Secrets (environment variables - NEVER written into any file in this repo):
#   ADMIN_PASSWORD        required  full-access password for /admin
#   CHECKIN_KEY           required  long random token for the door check-in link
#                                   (make one with:  openssl rand -hex 16)
#   VIEW_ONLY_PASSWORD    optional  read-only login for /admin
#   GMAIL_APP_PASSWORD    optional  needed for any email to be sent
#   STRIPE_SECRET_KEY     optional  set it to switch card payments on
#   STRIPE_WEBHOOK_SECRET optional  from the Stripe webhook (README step 7)
# Other settings:
#   AWS_REGION            default us-east-1
#   ARTIFACT_BUCKET       S3 bucket SAM uploads code to (default: SAM creates one)
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
REGION="${AWS_REGION:-us-east-1}"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# --- secrets: required ones present, and safe to pass on a command line ---------
[ -n "${ADMIN_PASSWORD:-}" ] || fail "ADMIN_PASSWORD is not set. Add it as a GitHub secret (README step 5)."
[ -n "${CHECKIN_KEY:-}" ]    || fail "CHECKIN_KEY is not set. Add it as a GitHub secret (README step 5)."
GMAIL_APP_PASSWORD="$(printf '%s' "${GMAIL_APP_PASSWORD:-}" | tr -d ' ')"   # Google shows it with spaces; SMTP wants none
for name in ADMIN_PASSWORD VIEW_ONLY_PASSWORD CHECKIN_KEY GMAIL_APP_PASSWORD STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET; do
  value="${!name:-}"
  if [[ "$value" =~ [[:space:]\"\'\,\\] ]]; then
    fail "$name contains a space, quote, comma or backslash. Use a value with letters, numbers and simple symbols only."
  fi
done
[ ${#ADMIN_PASSWORD} -ge 10 ] || fail "ADMIN_PASSWORD is too short - use at least 10 characters."
[ ${#CHECKIN_KEY} -ge 16 ]    || fail "CHECKIN_KEY is too short - use at least 16 characters (openssl rand -hex 16)."
[ -n "${VIEW_ONLY_PASSWORD:-}" ] || echo "note: VIEW_ONLY_PASSWORD not set - the read-only login is disabled."
[ -n "${GMAIL_APP_PASSWORD}" ]   || echo "note: GMAIL_APP_PASSWORD not set - no emails will be sent until you add it."
[ -n "${STRIPE_SECRET_KEY:-}" ]  || echo "note: STRIPE_SECRET_KEY not set - card payments are OFF (Venmo/Zelle only)."

say "Checking chapter.config.yaml"
python3 scripts/prepare.py --strict --check
STACK="$(python3 scripts/prepare.py --get chapter_id)"

say "Preparing the build for '$STACK'"
python3 scripts/prepare.py

# --- parameters: non-secret ones come from chapter.config.yaml -------------------
PARAMS=()
while IFS= read -r line; do PARAMS+=("$line"); done < <(python3 scripts/prepare.py --sam-params)
PARAMS+=("AdminPassword=${ADMIN_PASSWORD}" "CheckinKey=${CHECKIN_KEY}")
# Optional secrets: only passed when set (unset = the template's blank default).
[ -z "${VIEW_ONLY_PASSWORD:-}" ]    || PARAMS+=("ViewOnlyPassword=${VIEW_ONLY_PASSWORD}")
[ -z "${GMAIL_APP_PASSWORD}" ]      || PARAMS+=("GmailAppPassword=${GMAIL_APP_PASSWORD}")
[ -z "${STRIPE_SECRET_KEY:-}" ]     || PARAMS+=("StripeSecretKey=${STRIPE_SECRET_KEY}")
[ -z "${STRIPE_WEBHOOK_SECRET:-}" ] || PARAMS+=("StripeWebhookSecret=${STRIPE_WEBHOOK_SECRET}")

say "Building the backend (sam build)"
( cd infra-tickets && sam build )

say "Deploying the stack '$STACK' to $REGION (sam deploy) - the first time this takes 10-15 minutes"
BUCKET_ARGS=(--resolve-s3)
if [ -n "${ARTIFACT_BUCKET:-}" ]; then BUCKET_ARGS=(--s3-bucket "$ARTIFACT_BUCKET" --s3-prefix "$STACK"); fi
( cd infra-tickets && sam deploy \
    --stack-name "$STACK" \
    --region "$REGION" \
    --capabilities CAPABILITY_IAM \
    --no-confirm-changeset \
    --no-fail-on-empty-changeset \
    --tags "app=punarmilan" "chapter=$STACK" \
    "${BUCKET_ARGS[@]}" \
    --parameter-overrides "${PARAMS[@]}" )

out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
          --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text; }
SITE_URL="$(out SiteUrl)"; BUCKET="$(out SiteBucketName)"; DIST_ID="$(out DistributionId)"
[ -n "$BUCKET" ] && [ "$BUCKET" != "None" ] || fail "Could not read the stack outputs - did the deploy succeed?"

say "Building the website"
python3 scripts/write_frontend_env.py "$STACK" "$REGION"
( cd frontend-tickets && npm ci --no-audit --no-fund && npm run build )

say "Publishing the website to S3 and refreshing CloudFront"
aws s3 sync frontend-tickets/dist "s3://$BUCKET" --delete --region "$REGION"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" >/dev/null

WEBHOOK_URL="$(out WebhookEndpoint)"; ADMIN_EP="$(out AdminEndpoint)"; INVITE_EP="$(out SendInviteEndpoint)"
SUMMARY=$(cat <<EOF
## Deployed: $STACK

| | |
|---|---|
| Website | $SITE_URL |
| Admin page | $SITE_URL/admin |
| Door check-in | $SITE_URL/checkin?key=<your CHECKIN_KEY secret> |

**Stripe webhook URL** (only if you take card payments - README step 7):
\`$WEBHOOK_URL\`

**Google Sheets scripts** (README step 9) - Script Properties:
- ADMIN_ENDPOINT = \`$ADMIN_EP\`
- SEND_INVITE_ENDPOINT = \`$INVITE_EP\`

The first time, CloudFront can take a few more minutes to start serving the site.
EOF
)
echo; echo "$SUMMARY"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$SUMMARY" >> "$GITHUB_STEP_SUMMARY"; fi
say "Done."
