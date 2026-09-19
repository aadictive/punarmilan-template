# Troubleshooting

## Deploy problems

| Message | Cause / fix |
|---|---|
| `chapter.config.yaml is not valid YAML` | A quotation mark is missing or extra, or the indentation was changed. Compare with the sample at `tests/fixtures/sample.chapter.config.yaml`. |
| `... is empty - please fill it in.` | A required setting is blank. |
| `content/xxx.md uses {foo}, which isn't a known placeholder` | A typo in a `{placeholder}`; the message lists the valid ones. |
| `content/xxx.md has a stray comment marker` | A note in a content file (between `<!--` and `-->`) contains one of those markers inside itself. |
| `ModuleNotFoundError` / pytest failures on your own edits | Run the tests locally with `python3 -m pytest tests -q`; they only check the code and the sample config, so a failure after editing only your settings usually means a broken content/config file - the `prepare.py` message names it. |
| `AccessDenied` in `sam deploy` | Missing permission on the chapter's deploy login; send the message to the AWS owner (see Operator guide, first-deploy shakedown). |
| `Stack ... is in ROLLBACK_COMPLETE state and can not be updated` | A failed first deploy. The AWS owner (or the deployer key) runs `aws cloudformation delete-stack --stack-name <chapter_id>`, then re-run. |
| `Resource handler returned message: "... already exists"` | Two stacks tried to create the same named resource. Names come from the stack name, so this means a leftover from an earlier failed run - delete the leftover or use a different `chapter_id`. |
| Deploy succeeds but site is blank | CloudFront needs a few minutes on the first deploy; hard-refresh. Check `frontend-tickets/.env.production` wasn't empty (the step "Building the website" prints `wrote ... (14 endpoints)`). |

## Payments

| Symptom | Cause / fix |
|---|---|
| Card payment works but registration stays `pending_payment`, no ticket email | The Stripe **webhook** is missing, points at the wrong URL, listens to the wrong event (needs `checkout.session.completed`), or `STRIPE_WEBHOOK_SECRET` is from the other mode (test vs live secrets differ). Check the webhook's delivery log in Stripe. Until it's fixed, use **Mark paid** in `/admin` for those attendees. |
| "Card payments aren't set up yet" shown to attendees | `STRIPE_SECRET_KEY` secret isn't set (or the deploy hasn't run since you set it). |
| Stripe checkout says the amount is wrong | Ticket price is set in dollars in `tickets.price_usd`; the card option adds Stripe's fee on top so you net the full price - that's expected. |
| Venmo/Zelle QR shows a "REPLACE THIS IMAGE" picture | You didn't replace `assets/venmo-qr.png` / `zelle-qr.png` (the deploy normally blocks this when the handle is set). |

## Email

| Symptom | Cause / fix |
|---|---|
| `Marked paid, but the confirmation email failed to send: (421 ... Temporary System Problem)` | Gmail briefly refused the connection (throttling). The payment **is** recorded. Wait a few minutes and use the admin **Emails** tab -> **Resend confirmation** for that person. |
| `(535 ... Username and Password not accepted)` | `GMAIL_APP_PASSWORD` is wrong, was revoked, or isn't for the account in `email.sender_email`; it also needs 2-Step Verification on. Fix the secret and re-run the deploy. |
| `(550 5.4.5 Daily user sending limit exceeded)` | Gmail's ~500/day cap. Wait 24h, spread invites over more days, or use a Google Workspace account. |
| Emails land in spam | Send a few test messages first, avoid all-caps/spammy wording in your content, and keep the batch pace modest. |

## Admin / check-in

| Symptom | Cause / fix |
|---|---|
| "Incorrect password" on `/admin` | It must equal the current `ADMIN_PASSWORD` / `VIEW_ONLY_PASSWORD` secret **as of the last deploy**. Changed a secret? Re-run **Deploy site**. |
| Buttons greyed out | You logged in with the view-only password. |
| Check-in: "invalid or expired" | The `?key=` in the link doesn't match the current `CHECKIN_KEY` secret. |
| Camera won't start | The browser blocked camera permission, or the page isn't loaded over `https`. Use the typed reference code as a fallback. |
| Someone says they registered but you can't find them | Search by email (all lowercase); check the **Interests** count on the Stats tab includes people who only *viewed* the price. |

## Google Sheets scripts

| Symptom | Cause / fix |
|---|---|
| Registrations tab shows `Error: Admin endpoint returned 401` | `ADMIN_PASSWORD` script property isn't your current admin password. |
| Nothing is being sent | Outside 9am-9pm the trigger sleeps by design; check **Executions** (Apps Script sidebar) for errors, confirm `SEND_INVITE_ENDPOINT` is set, and that test mode is off/on as you intend. |
| Rows keep saying "Invite sent" though people registered | `ADMIN_ENDPOINT` script property is missing (reconciliation is skipped silently without it). |
