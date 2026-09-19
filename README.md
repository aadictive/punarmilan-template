# Punarmilan - The Reunion

*पुनर्मिलन — "reunion"*

A ready-made website for running an alumni reunion: people register, pay by card
or Venmo/Zelle, get an e-ticket with a QR code by email, and you scan them in at
the door. You get an admin page to manage everything, invite emails you can send
to your alumni list, and an optional Google Sheet dashboard.

**You do not need to write code.** You edit a settings file and a couple of text
files in your web browser, paste a few passwords into GitHub, and the site builds
and publishes itself.

- [What you get](#what-you-get)
- [How it works](#how-it-works)
- [Before you start](#before-you-start)
- [Step 1 - Make your own copy](#step-1---make-your-own-copy)
- [Step 2 - Turn on GitHub Actions](#step-2---turn-on-github-actions)
- [Step 3 - Fill in chapter.config.yaml](#step-3---fill-in-chapterconfigyaml)
- [Step 4 - Your words and your pictures](#step-4---your-words-and-your-pictures)
- [Step 5 - Add your passwords (GitHub Secrets)](#step-5---add-your-passwords-github-secrets)
- [Step 6 - Publish the site (first deploy)](#step-6---publish-the-site-first-deploy)
- [Step 7 - Turn on card payments (Stripe)](#step-7---turn-on-card-payments-stripe)
- [Step 8 - Test everything before you announce it](#step-8---test-everything-before-you-announce-it)
- [Step 9 - Google Sheet dashboard and invite emails](#step-9---google-sheet-dashboard-and-invite-emails)
- [Step 10 - Event day: check-in](#step-10---event-day-check-in)
- [Changing things later](#changing-things-later)
- [Reference](#reference): [placeholders](#placeholders-you-can-use-in-your-text) · [costs](#what-it-costs) · [security](#security-and-who-should-have-access) · [troubleshooting](#troubleshooting) · [repo layout](#whats-in-this-repository)
- [If you look after the AWS account](#if-you-look-after-the-aws-account)

---

## What you get

| For attendees | For you (the organiser) |
|---|---|
| A registration page with your event details, venue and photo | An **admin page** (`/admin`): search, filter, mark paid, refund, check in, export to CSV |
| Pay by **card** (Stripe), **Venmo** or **Zelle** | A **stats tab** kept separate so money figures aren't on screen by accident |
| A confirmation email with a **QR-code e-ticket** | **Payment reminders** and **event-reminder** emails, sent in bulk or one by one |
| A one-click **"Can't make it"** page (from invite emails) | **Invite emails** to your alumni list, paced so they aren't flagged as spam |
| | A **door check-in page** for volunteers' phones (scan the ticket QR) |
| | An optional **Google Sheet** that mirrors registrations with a live dashboard |

Everything is "serverless" on AWS: nothing to patch or keep running, and at
chapter scale it costs a few dollars, often less than one (see [costs](#what-it-costs)).

## How it works

```
   you edit files on GitHub  ──►  GitHub Action  ──►  your site is live
   (settings, text, images)      (builds + deploys)     https://xxxx.cloudfront.net

   chapter.config.yaml   event, venue, price, contact
   content/*.md          your intro text, invite-email opening, message drafts
   assets/               your photo + Venmo/Zelle QR screenshots
   GitHub Secrets        passwords and keys (never in a file)
```

Every time you save a change to the `main` branch, the Action re-checks your
settings, runs the tests, and republishes the site - usually 5-10 minutes (the
first time, about 15).

## Before you start

You need:

- [ ] A **GitHub account** (free) - [github.com/signup](https://github.com/signup)
- [ ] **Access to this template**, and someone who has given you the two **AWS keys** for your chapter (see [If you look after the AWS account](#if-you-look-after-the-aws-account); if that's you, do that part first)
- [ ] A **Gmail account for your chapter's emails** - a dedicated one is best (a normal Gmail can send about 500 emails a day). It needs 2-Step Verification switched on.
- [ ] For card payments: a **Stripe account** ([stripe.com](https://stripe.com), free to open; you can start in "test mode" with no real money moving). Skip this for a Venmo/Zelle-only site.
- [ ] For Venmo / Zelle: the **handle** you receive payments on, and a **screenshot of your QR code** from your Venmo / bank app
- [ ] Your event details: date, time, venue name and address, ticket price, who attendees should contact, a good photo
- [ ] About **an hour** for the first setup

No programs to install. Everything below happens in your web browser.

---

## Step 1 - Make your own copy

1. Open the template's page on GitHub and click the green **Use this template** button, then **Create a new repository**.
2. Choose a name (for example `punarmilan-chicago`), and select **Private**. *Keep it private* - see [security](#security-and-who-should-have-access).
3. Click **Create repository**.

You now have your own copy. Everything from here happens in **your** copy.

> Are you a developer and prefer git? Clone it, edit the same files, and push - the result is identical.

## Step 2 - Turn on GitHub Actions

Open your repository and click the **Actions** tab. If GitHub shows a green button
saying workflows are disabled or asks you to enable them, click it. You should see
a workflow called **Deploy site**. It will fail until you finish Step 5 - that's
expected.

## Step 3 - Fill in chapter.config.yaml

This one file holds all of your event's details.

1. In your repository, click the file **`chapter.config.yaml`**.
2. Click the **pencil icon** (top right of the file) to edit it in the browser.
3. Change the text between the quotation marks. Lines starting with `#` are notes - leave them.
4. Click **Commit changes...** and then **Commit changes** (leave "commit directly to the main branch" ticked).

(Each commit starts a deploy, which will fail until Step 5 is done. That's fine - you can make several edits, or just finish Step 5 and then re-run the deploy.)

### What each setting means

| Setting | What to put | Example |
|---|---|---|
| `chapter_id` | A short id for your site: lowercase letters, numbers, hyphens, 3-20 characters, starting with a letter. **You cannot change this later** without creating a new site. Use the id the person who looks after AWS created your keys for. | `somaiya-chicago` |
| `product_name` | Leave as it is | |
| `chapter_name` | Your chapter's full name, used in email signatures | `Somaiya Chicago Alumni Chapter` |
| `event.name` | The event's name | `Somaiya Alumni Meet` |
| `event.date` | The date as **YYYY-MM-DD**. The weekday, "October 18, 2026", "Oct 18" and the calendar badge are all worked out from it. | `2026-10-18` |
| `event.time` | Start and end, as you want it displayed | `12:00 PM – 4:00 PM` |
| `event.city` | Small heading above the event name | `Chicago` |
| `event.venue_name` / `venue_address` | The venue | `The Grand Hall` / `10 Main St, Chicago, IL 60601` |
| `event.venue_maps_url` | A Google Maps share link. Leave `""` to hide "Get directions". | `https://maps.app.goo.gl/...` |
| `contact.name` / `title` / `phone` / `email` | Who attendees should reach out to. Shown on the site and in every email. | `Riya Rao`, `Chapter Lead` |
| `whatsapp_group_url` | Your WhatsApp group invite link. Leave `""` and that line is simply left out of emails. | `https://chat.whatsapp.com/...` |
| `short_link` | A short link that points to your site (from any link shortener), if you make one - only used to fill in the message drafts. | `https://short.example/...` |
| `tickets.price_usd` | Price per ticket in US dollars | `65` or `65.50` |
| `payments.venmo_handle` / `zelle_handle` | Where you receive payments. Leave `""` to switch that option **off**. | `@your-chapter` / `you@example.org` |
| `email.sender_email` | The Gmail address emails are sent **from** | `events@your-chapter.example` |
| `registration_form.expectation_options` | The "What are you most looking forward to?" tick-boxes (2 to 8) | |
| `registration_form.college_placeholder` | Grey hint text in the "College" box | `e.g. KJSCE` |

**Card payments** have no setting here: they switch on by themselves when you add
the `STRIPE_SECRET_KEY` secret in Step 5. Leave it out for a Venmo/Zelle-only site.

**If you make a mistake**, the deploy stops and the Action's log tells you, in
plain English, exactly what to fix (for example *"event.date must look like
2026-10-18"*). Nothing half-broken ever goes live.

## Step 4 - Your words and your pictures

### The text in `content/`

Open the **`content`** folder. Each file starts with a note to you (between the
`<!--` and `-->` lines) explaining what it's for.

| File | Where it appears |
|---|---|
| `hero_blurb.md` | The intro paragraphs on the left of the registration page |
| `invite_email.md` | The opening paragraphs of the invite email |
| `whatsapp_message.md` | A ready-to-paste WhatsApp announcement (not used by the site) |
| `linkedin_post.md` | A ready-to-paste LinkedIn post (not used by the site) |

**How to write:** just write sentences. A blank line starts a new paragraph.
`**double stars**` make bold, `*single stars*` make italic, `[link text](https://link)`
makes a link. Words in `{curly brackets}` are filled in for you - see
[placeholders](#placeholders-you-can-use-in-your-text). You can't break the page
with any of this, and any HTML you type is shown as plain text, not run.

After each deploy, the filled-in WhatsApp and LinkedIn drafts are attached to the
Action run: open the run and download **message-drafts** from the *Artifacts* section
at the bottom of the run page.

### The pictures in `assets/`

Replace these files by opening the **`assets`** folder, clicking **Add file -> Upload files**,
dragging your file in with **exactly the same file name**, and committing:

| File | What it is |
|---|---|
| `event-photo.jpg` | The photo behind the intro text. Landscape works best; under 2 MB. A photo from a past event is ideal. |
| `venmo-qr.png` | A screenshot of **your own** Venmo QR code |
| `zelle-qr.png` | A screenshot of **your own** Zelle QR code |

**Getting a clean QR screenshot:** open your Venmo or bank app, open "Scan / Receive / My QR code", take a screenshot, then crop it square around the QR code (your phone's photo editor can do it). The QR codes are real pictures from your own app on purpose - that is what makes them scan reliably.

If you switch Venmo or Zelle **on** but leave the placeholder picture in place,
the deploy stops and tells you - attendees are never shown a "REPLACE THIS IMAGE" picture.

## Step 5 - Add your passwords (GitHub Secrets)

Secrets are passwords that GitHub stores encrypted. They are used during the
deploy and are **never** shown in logs or written into any file.

Go to your repository -> **Settings** -> **Secrets and variables** -> **Actions**.
On the **Secrets** tab click **New repository secret** for each row below (type the
name exactly as shown, paste the value, click **Add secret**):

| Secret name | Required? | What it is / how to get it |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | **Yes** | Given to you by the person who looks after the AWS account |
| `AWS_SECRET_ACCESS_KEY` | **Yes** | Same - given to you privately, together with the line above |
| `ADMIN_PASSWORD` | **Yes** | The password you'll use to log in to the admin page. **Make up your own**: at least 10 characters. Avoid spaces, quotes, commas and backslashes. |
| `CHECKIN_KEY` | **Yes** | A long random code that protects the door check-in link. At least 16 characters, letters and numbers only. A random one is best: on a Mac/Linux terminal run `openssl rand -hex 16`, or use any password manager's generator (letters and numbers, 32 characters). |
| `VIEW_ONLY_PASSWORD` | Optional | A second password that can *look* but not change anything (great for volunteers). Leave it out to disable that login. |
| `GMAIL_APP_PASSWORD` | Needed for any email | An "App Password" for the Gmail account in `email.sender_email` - see below |
| `STRIPE_SECRET_KEY` | For card payments | Starts with `sk_test_` (test) or `sk_live_` (real money) - see [Step 7](#step-7---turn-on-card-payments-stripe) |
| `STRIPE_WEBHOOK_SECRET` | For card payments | Starts with `whsec_` - see [Step 7](#step-7---turn-on-card-payments-stripe) |

Then, on the **Variables** tab (next to Secrets), click **New repository variable** for:

| Variable name | Value |
|---|---|
| `ARTIFACT_BUCKET` | Given to you together with your AWS keys |
| `AWS_REGION` | Only if you were told a region other than `us-east-1` |

**Getting a Gmail App Password**
1. Sign in to the Gmail account you'll send from. Turn on **2-Step Verification** (Google Account -> Security) if it isn't already.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), name it "Punarmilan", and click **Create**.
3. Google shows a 16-letter password (with spaces). Paste it as the `GMAIL_APP_PASSWORD` secret. Spaces are fine - they're removed for you.

> **Never** put a password in `chapter.config.yaml`, in the content files, in an issue, or in a chat. If you ever paste one somewhere by accident, change it and update the secret.

## Step 6 - Publish the site (first deploy)

1. Go to the **Actions** tab -> click **Deploy site** in the left list -> **Run workflow** -> **Run workflow** (green).
   (Any later commit to `main` does this automatically.)
2. Click the run that appears to watch it. The first time takes **10-15 minutes** - AWS is creating your database, your functions, and the website hosting.
3. When it finishes with a green tick, open the run and scroll down to the **summary**. It lists:
   - your **website address** (`https://xxxxxxxx.cloudfront.net`) - open it
   - your **admin page** (`.../admin`) - log in with `ADMIN_PASSWORD`
   - your **check-in link** (`.../checkin?key=YOUR-CHECKIN_KEY`)
   - your **Stripe webhook address** (for [Step 7](#step-7---turn-on-card-payments-stripe))
   - two values for the [Google Sheet scripts](#step-9---google-sheet-dashboard-and-invite-emails)
4. If the site shows a blank page or an error in the first few minutes, wait a little and refresh - CloudFront can take a few minutes to start serving.

**A red cross?** Click the failed step - the message says what to fix. The most common ones are in [troubleshooting](#troubleshooting). Fix it, then **Re-run** the workflow.

## Step 7 - Turn on card payments (Stripe)

Skip this if you only take Venmo/Zelle.

1. In the Stripe dashboard, use the **Test mode** switch (top right) for your first run. Go to **Developers -> API keys** and copy the **Secret key** (`sk_test_...`). Add it as the `STRIPE_SECRET_KEY` secret.
2. **Run the Deploy workflow again** so the site learns about the key. (This prints your webhook address in the summary.)
3. In Stripe: **Developers -> Webhooks -> Add endpoint**.
   - **Endpoint URL:** the *Stripe webhook address* from the deploy summary
   - **Events:** select `checkout.session.completed`
   - Save it, then click **Reveal** next to **Signing secret** (`whsec_...`).
4. Add that as the `STRIPE_WEBHOOK_SECRET` secret and **run the Deploy workflow once more**.

> **This webhook is not optional.** Without it, attendees can pay and Stripe takes their money, but their registration never flips to *Paid* and no ticket is emailed. The site can't tell you it's missing - so do the test in Step 8.

**Going live with real money:** when you've tested, switch Stripe to **Live mode**, repeat steps 1-4 with the **live** key (`sk_live_...`) and a **new webhook created in live mode** (test and live webhooks have different signing secrets), update both secrets, and re-run the deploy.

## Step 8 - Test everything before you announce it

Do this with your own email addresses, in Stripe **Test mode** (use card `4242 4242 4242 4242`, any future date, any 3 digits):

- [ ] Open the site: event name, date, venue, photo, contact details and your intro text all look right, on your phone too
- [ ] Register with a test email; the price is right; the payment options you enabled show up
- [ ] **Card:** pay with the test card; you land on the "You're all set!" page; the registration shows **Paid** in `/admin` within a few seconds; the confirmation email arrives with a QR code
- [ ] **Venmo/Zelle:** the QR picture is *yours*; choosing "Email me these instructions" delivers an email; in `/admin`, **Mark paid** sends the confirmation email
- [ ] The e-ticket QR scans on your phone at the check-in link
- [ ] `/admin` -> **Stats** and **Emails** tabs open; **Export CSV** downloads
- [ ] The **View only** login (if you set one) can look but every action button is greyed out
- [ ] Refund one test registration in `/admin`; the refund email arrives
- [ ] Emails aren't landing in spam (check the spam folder once)

When everything passes: switch Stripe to live (Step 7), refund or ignore your test registrations, and announce your link.

## Step 9 - Google Sheet dashboard and invite emails

Optional, and it takes about 20 minutes. Full walkthrough: **[docs/SHEETS-AND-INVITES.md](docs/SHEETS-AND-INVITES.md)**.

- **`tools/google-sheets-sync.gs`** mirrors registrations into a Google Sheet every minute, colour-coded by status, with a dashboard tab.
- **`tools/invite-mail-merge.gs`** sends personalised invites to your alumni list, at a gentle pace.

**Who actually sends the invite emails?** Not Google. The script only reads your list and, one person at a time, asks *your site's backend* to send that person an email through your Gmail account - with their name in the greeting and "Yes, I'll be there" / "Can't make it" links carrying their details. Google Apps Script is just a free scheduler here. You can swap it for any other tool that can make a web request (Zapier/Make/n8n, a short script) or a proper mailing tool - the alternatives are listed at the top of the script and in the walkthrough.

## Step 10 - Event day: check-in

1. Share the **check-in link** (`.../checkin?key=YOUR-CHECKIN_KEY`) with your volunteers. Opening it once on a phone remembers the key; bookmark it or "add to home screen".
2. Volunteers tap **Start scanning** and point the camera at each attendee's e-ticket QR. A pop-up shows the person's name and a green tick, an amber warning (already scanned, or not paid), or a red message (unknown code). **Scan more** carries on; **OK** stops the camera.
3. No camera? Type the 8-character code from the ticket instead.
4. In `/admin` you can also check someone in or undo a check-in by hand.

Anyone with the check-in link can check people in, so don't post it publicly.

---

## Changing things later

Edit, commit, done - the Action republishes. Typical changes:

| I want to... | Edit |
|---|---|
| Change the price | `tickets.price_usd` in `chapter.config.yaml` (existing registrations keep the price they signed up at) |
| Change time/venue | `event.time`, `event.venue_*` |
| Change my intro text or invite wording | `content/hero_blurb.md`, `content/invite_email.md` |
| Replace a QR code or the photo | Upload over the file in `assets/` |
| Change a password / key | Update the **Secret**, then re-run **Deploy site** |
| Turn card payments off | Delete the `STRIPE_SECRET_KEY` secret and re-run |
| Run a new event next year | Change `event.date` and the text - keep the same `chapter_id` and the same site. (Old registrations stay in the database; ask whoever looks after AWS if you want a fresh start.) |

## Reference

### Placeholders you can use in your text

Type these in `{curly brackets}` inside any file in `content/`:

| Placeholder | Becomes |
|---|---|
| `{event_name}` | `event.name` |
| `{event_date}` | Sunday, October 18, 2026 |
| `{event_date_short}` | Oct 18 |
| `{event_time}` | `event.time` |
| `{city}` | `event.city` |
| `{venue_name}`, `{venue_address}`, `{venue_maps_url}` | the venue settings |
| `{chapter_name}`, `{product_name}` | the names |
| `{contact_name}`, `{contact_title}`, `{contact_phone}`, `{contact_email}` | the contact settings |
| `{ticket_price}` | `$65` |
| `{registration_link}` | your `short_link` (or a reminder to add one) |

A typo such as `{evnt_name}` is caught at deploy time and reported by name.

### What it costs

Typical chapter event (a few hundred attendees): **AWS is usually well under $5 for the whole event** - it's pay-per-use, and the database, functions and hosting sit largely inside AWS's monthly free amounts. The database is kept even if you delete the site (deliberately, so attendee data can't vanish by accident) and costs cents a month. **Stripe** takes its normal card fee from each card payment (the site adds it on top of the ticket price so you net the full price - attendees see this before paying). Venmo/Zelle have no fee. Gmail sending is free.

### Security and who should have access

- The Action deploys with your passwords, so **anyone who can push to `main` can read your secrets** (by editing the workflow). Keep the repo **private**, and only add people you'd trust with those keys. Volunteers don't need GitHub access at all - they use the `/admin` view-only login and the check-in link.
- The two AWS keys you were given can only deploy **your own chapter's site**, not other chapters' sites - but treat them like passwords all the same.
- Passwords are checked by the backend, not just hidden in the page. The view-only login genuinely cannot change anything.
- Attendee emails, phone numbers and payment status live in your database. Export CSVs sparingly and delete downloaded copies.
- If a key or password leaks: change it (Stripe: roll the key; others: update the GitHub Secret) and re-run the deploy.

### Troubleshooting

| What you see | What to do |
|---|---|
| Deploy fails at "Check the settings file" with a list of fixes | Read the list - each line says which setting is wrong. Fix, commit. |
| `ADMIN_PASSWORD is not set` / `CHECKIN_KEY is not set` | Add that secret (Step 5), then re-run. |
| `...contains a space, quote, comma or backslash` | Pick a value using only letters, numbers and simple symbols like `- _ . !`. |
| `assets/venmo-qr.png is still the placeholder picture` | Upload your real QR image (Step 4), or clear `payments.venmo_handle`. |
| `AccessDenied` / `not authorized to perform ...` in the deploy log | The AWS keys or their permissions don't match your `chapter_id`. Send the exact message to whoever looks after AWS. |
| A stack in `ROLLBACK_COMPLETE`, or "already exists" | Tell the AWS owner - a failed *first* deploy has to be cleared once before retrying. |
| Site shows a blank page right after the first deploy | Wait 5 minutes and hard-refresh. |
| Paid by card but the registration stays *pending* | The webhook is missing or wrong: recheck Step 7 (endpoint address, the `checkout.session.completed` event, and that the secret matches the *same* mode - test/live). |
| No emails arrive | Check `GMAIL_APP_PASSWORD` is set and belongs to `email.sender_email`; check spam; confirm 2-Step Verification is on. The admin page shows a warning when a send fails. |
| Emails come from the wrong name/address | They're sent from `email.sender_email`; set the display name in that Gmail account's settings. |
| Login to `/admin` says "Incorrect password" | It's the value of the `ADMIN_PASSWORD` (or `VIEW_ONLY_PASSWORD`) secret **as of the last deploy** - re-run the deploy after changing a secret. |
| Check-in says the link is invalid or expired | The `key=` in the link must equal the `CHECKIN_KEY` secret as of the last deploy. |
| Everything's right but a change isn't showing | Deploys take a few minutes; hard-refresh (Cmd/Ctrl+Shift+R). |

More: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### What's in this repository

```
chapter.config.yaml        <- your event's settings (edit this)
content/                   <- your text (edit these)
assets/                    <- your photo + QR screenshots (replace these)
.github/workflows/deploy.yml   the Action that publishes the site
scripts/prepare.py         checks your settings, builds the config the site reads
scripts/deploy.sh          builds and deploys everything (the Action runs this)
scripts/admin/             for the AWS-account owner: create-chapter-deployer.sh
backend-tickets/           the server code (registration, payments, emails, admin, check-in)
frontend-tickets/          the website (React)
infra-tickets/template.yaml    the AWS resources (database, functions, hosting)
tools/                     Google Apps Scripts (dashboard sync, invite mail-merge)
tests/                     automated tests that run before every deploy
docs/                      operator guide, Sheets/invites walkthrough, troubleshooting
```

`generated/`, `backend-tickets/chapter_config.json` and `frontend-tickets/src/chapter.generated.json`
are built from your settings on every deploy and are not stored in git.

### Running it on your own computer (optional, for developers)

```bash
pip install -r requirements-dev.txt
python3 scripts/prepare.py            # validates + generates
python3 -m pytest tests -q
cd frontend-tickets && npm ci && npm run dev
```

Deploying by hand: export the secrets from Step 5 as environment variables, configure the AWS CLI, then `bash scripts/deploy.sh`.

---

## If you look after the AWS account

Chapters can deploy into an AWS account you own without having any AWS knowledge. You create one
narrowly-scoped deploy login per chapter, and hand its two keys to that chapter lead:

```bash
scripts/admin/create-chapter-deployer.sh <chapter_id> <artifact-bucket>
```

Full checklist (one-time account setup, onboarding a chapter, what to check on the first deploy,
offboarding, and the honest list of what this permission model does and doesn't protect against):
**[docs/OPERATOR-GUIDE.md](docs/OPERATOR-GUIDE.md)**.

A chapter can equally deploy into **its own** AWS account: they run the same Action with their own
keys (any IAM user allowed to deploy CloudFormation/Lambda/DynamoDB/S3/CloudFront) and don't need the
scripts in `scripts/admin/`.
