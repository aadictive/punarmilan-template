# Google Sheet dashboard and invite emails

Two optional Google Apps Scripts live in `tools/`. Both talk to your site's backend; neither
sends email itself.

| Script | What it does |
|---|---|
| `google-sheets-sync.gs` | Copies all registrations into a **Registrations** tab every minute, colour-coded by status, and builds a **Dashboard** tab (KPI tiles + charts). |
| `invite-mail-merge.gs` | Reads your alumni list from a **Database** tab and asks the backend to send each person a personalised invite, a few at a time. |

## 1. Create the sheet

1. Create a new Google Sheet. Add a tab named **Database** with this header row (exactly these names, any
   order is fine):

   | Alumni Name | Email Address | Contact Number | Status | Follow up Details |
   |---|---|---|---|---|

   Paste your alumni list underneath. Leave **Status** blank - the script fills it in. **Follow up Details**
   is for your team's own notes; the scripts never touch it. One email per row (put someone with two
   addresses on two rows).
2. **Extensions -> Apps Script.** Delete the sample code, create a file and paste in `tools/google-sheets-sync.gs`.
   Add a second file with `tools/invite-mail-merge.gs`. (Both files can live in the same project; they're
   written so their names don't collide.)
3. **Project Settings (gear) -> Script Properties -> Add** these (values are in your deploy summary):

   | Property | Value |
   |---|---|
   | `ADMIN_ENDPOINT` | from the deploy summary |
   | `ADMIN_PASSWORD` | your admin password |
   | `SEND_INVITE_ENDPOINT` | from the deploy summary |

4. In the editor's function dropdown choose **`setupSync`** -> Run (approve the permissions). Then
   **`setupInvites`** -> Run. Reload the sheet: you'll see **Registrations** and **Invites** menus.

## 2. How invites are sent (and what else you could use)

`invite-mail-merge.gs` does not send email. Each time its timer fires it takes the next few unsent rows and,
for each person, calls the backend's "send invite" URL with their name and email. The backend builds a
personalised message (their name, your opening text from `content/invite_email.md`, your event details, a
"Yes, I'll be there" button that opens the registration form pre-filled with their name and email, and a
"Can't make it this year?" button) and sends it through your Gmail account. The script then writes
`Invite sent <time>` in the row's **Status**.

Why route through the backend instead of Apps Script's own mail service? A regular Gmail account can send only
about 100 emails/day from Apps Script (`MailApp`/`GmailApp`) but about 500/day over SMTP, which is what the
backend uses - and it keeps every email (confirmations, reminders, invites) coming from one place with one
look.

Other ways to run the same job:

- **Any scheduler that can make a web request** (Zapier, Make, n8n, a cron job, a 10-line Python/Node
  script): `POST` to your `SEND_INVITE_ENDPOINT` with header `X-Admin-Password: <admin password>` and JSON body
  `{"name": "Ann Lee", "email": "ann@example.org"}`.
- **A dedicated mailing tool** (Mailchimp, Brevo, Google Workspace's mail merge) - larger lists and open/click
  stats, but you lose the automatic Registered/Declined tracking below and must build your own email.
- **An AWS scheduled function** (EventBridge + Lambda) that reads your list itself - needs a small code change.

## 3. The pacing (and testing it)

Defaults (top of `invite-mail-merge.gs`): **12 emails every 30 minutes, 9am-9pm** - about 288 a day, under
Gmail's daily cap and gentle enough not to look like bulk mail. Edit `BATCH_SIZE`,
`SEND_INTERVAL_MINUTES` (must be 1, 5, 10, 15 or 30) or the business-hour constants, then re-run
`setupInvites`.

Test on a copy of your sheet first (a few rows with your own addresses). Because the trigger sleeps outside
business hours, use **Invites -> Toggle test mode** to make it send at any hour, and turn it **off** again
before the real run (it toasts the state each time). **Invites -> Send next batch now** sends one batch
immediately.

## 4. What the Status column tells you

| Status | Meaning |
|---|---|
| *(blank)* | Not invited yet |
| `Invite sent <time>` | Email handed to Gmail |
| `No email — contact directly` | The row has no email - your manual follow-up list |
| `Error: ...` | That send failed; the message says why |
| `Registered (paid / pending_payment / viewed_price)` | They registered on the site (from any route - invite link, WhatsApp link...) |
| `Declined <time>` | They clicked "Can't make it" and confirmed |

Once someone registers by any route, the script marks them `Registered` and stops emailing them,
even if their turn hasn't come up yet.

## 5. Protect the sheet from accidental edits (recommended if others have edit access)

Your scripts run as **your** Google account, so protecting a range to "Only you" doesn't block them.
**Data -> Protect sheets and ranges:**

- Protect the **Registrations** and **Dashboard** tabs (whole sheet) -> only you.
- On **Database**, protect columns **A:D** (name, email, phone, status) -> only you, and leave
  **Follow up Details** unprotected so the team can add notes.

## 6. Stopping

**Invites -> Stop sending** removes both triggers (sending and reconciliation). Run `setupInvites` again to resume.
