# Punarmilan

*पुनर्मिलन — "reunion"*

Registration, ticketing, and check-in platform built for the Somaiya NY/NJ
Alumni Chapter's reunion events. Serverless end to end (Lambda Function URLs,
DynamoDB, S3 + CloudFront), no servers to patch and effectively free to run
at chapter scale.

The repo holds two independent, fully separate deployments:

| | v1 — RSVP | v2 — Ticketing |
|---|---|---|
| Dir | `backend/`, `frontend/`, `infra/` | `backend-tickets/`, `frontend-tickets/`, `infra-tickets/` |
| Purpose | Simple free RSVP collection | Paid registration with card + Venmo/Zelle, e-tickets, door check-in |

v2 is the actively developed stack; v1 stays live untouched as the earlier,
simpler version.

## v2 feature set

- **Registration** — one form per attendee, phone number with a US/India
  country-code selector, duplicate-paid-email guard (blocks accidentally
  overwriting a confirmed registration), and a confirmation modal if someone
  tries to switch payment method after already picking one.
- **Payment** — Stripe Checkout for cards (the card-processing fee is
  algebraically grossed up so the chapter nets the exact ticket price, not a
  flat markup that can fall short) or Venmo/Zelle with QR codes for manual
  reconciliation.
- **E-tickets** — confirmation email with a scannable QR code, sent over
  Gmail SMTP (no third-party mail service, no sandbox recipient allowlist).
- **Door check-in** (`/checkin`) — link-authenticated (no password prompt,
  so any number of volunteers' phones can use the same link), scans the
  e-ticket QR via the phone camera or accepts a typed reference code, with a
  live running count.
- **Admin panel** (`/admin`) — search by name/email/code, mark/unmark paid,
  refund (with an automatic refund-confirmation email), send a payment
  reminder (includes a fresh Stripe Checkout link plus Venmo/Zelle
  switch-instructions), CSV export, and a live summary (registered / paid /
  checked-in / refunded / collected). Payment-status-changing actions are
  gated behind a confirm dialog + shared passcode, since the admin password
  itself may be shared with several volunteers.
- **Google Sheets sync** (`tools/google-sheets-sync.gs`) — an Apps Script
  that polls the admin API on a timer and mirrors registrations into a
  Sheet, color-coded by status, plus a dashboard tab with KPI tiles and
  charts. No AWS infrastructure required on top of what's already deployed.

## Architecture notes

- Lambda **Function URLs**, not API Gateway — cheaper and simpler for this
  traffic level. CORS is handled entirely in application code; the Function
  URL's own `Cors` config is deliberately left unset (setting both causes
  duplicate `Access-Control-Allow-Origin` headers that browsers reject,
  which curl won't catch).
- DynamoDB, single table per stack, partition key `email`.
- S3 + CloudFront with Origin Access Control — not a public bucket.
- SES was the original email backend; it's since been replaced with direct
  Gmail SMTP (`smtplib`, an account App Password) since SES sandbox mode
  only allows sending to pre-verified recipients, which doesn't work for a
  real attendee list.
- No `samconfig.toml` is checked in — deploys pass every parameter
  explicitly (see below) rather than relying on saved guided-deploy state.

## Deploying

Requires the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html), Python 3.12, Node.js, and AWS credentials configured.

```bash
# Backend + infra
cd infra-tickets   # or infra/ for v1
sam build
sam deploy --guided
```

`--guided` will prompt for every parameter in `template.yaml` — Stripe keys,
Venmo/Zelle handles, the Gmail sender address and App Password, the admin
password, the door check-in key, and the ticket price. Leave payment-related
parameters blank to launch with that method disabled; the site degrades
gracefully rather than erroring.

Note the Lambda Function URL outputs, then:

```bash
cd frontend-tickets   # or frontend/ for v1
cp .env.example .env.production
# fill in the endpoint URLs from the sam deploy output
npm install
npm run build
aws s3 sync dist/ s3://<your-bucket> --delete
aws cloudfront create-invalidation --distribution-id <your-distribution-id> --paths "/*"
```

### Gmail App Password

Email sending uses the sender account's own SMTP access, not a third-party
provider. Requires 2-Step Verification enabled on that Google account, then
Google Account → Security → App passwords → generate one for this project.

### Stripe

Test mode is safe to leave running indefinitely (`sk_test_...` key) — the
site clearly marks it and no real charges occur. Switch to a live key only
when ready to accept real payments.

## Repo layout

```
backend/            v1 Lambda handlers (RSVP + admin)
frontend/            v1 React/Vite site
infra/                v1 SAM template

backend-tickets/     v2 Lambda handlers (register, checkout, webhook, admin,
                      check-in, reminders, refunds, ...)
frontend-tickets/    v2 React/Vite site (registration, admin, check-in pages)
infra-tickets/        v2 SAM template

tools/
  google-sheets-sync.gs   Apps Script dashboard sync (see file header for setup)
```
