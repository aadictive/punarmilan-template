/**
 * Punarmilan - The Reunion — invite mail-merge (paced)
 * Bind this to whichever spreadsheet holds the alumni "Database" tab - that
 * can be its own separate spreadsheet, or the SAME spreadsheet as
 * google-sheets-sync.gs (just add this as a second file in that same Apps
 * Script project, and add a "Database" tab alongside Registrations/
 * Dashboard). Sends a personalized invite (register link + one-click
 * decline link) to each alumnus, throttled to BATCH_SIZE per run, only
 * during BUSINESS_HOURS, so ~400 people go out over a few days instead of
 * one burst that risks getting flagged as spam.
 *
 * HOW THE EMAILS ACTUALLY GET SENT (read this if you're wondering why a Google
 * script is involved at all): this script does NOT send any email itself. It
 * only reads your alumni list and, one person at a time, asks the site's own
 * backend service (the "send invite" function that was deployed with your
 * site) to send that person a personalised invite - their name in the greeting,
 * and "Yes" / "Can't make it" links that already carry their name and email.
 * The backend sends it through your Gmail account, exactly like the
 * confirmation emails. Apps Script is used only as a free, always-on scheduler
 * that walks the spreadsheet; it isn't required for the sending to work.
 *   Why not let Apps Script send with MailApp/GmailApp? A normal Gmail account
 *   is capped at about 100 such emails a day there, versus about 500 via SMTP.
 *   Other ways to do the same job, if you'd rather not use Google Sheets:
 *     - Call the backend's "send invite" URL (SEND_INVITE_ENDPOINT in your deploy
 *       summary) from any scheduler or script: POST {"name": "...", "email":
 *       "..."} with the header X-Admin-Password. A short Python/Node loop or a
 *       Zapier/Make/n8n "spreadsheet row -> HTTP request" automation works the
 *       same way.
 *     - Use a dedicated mailing tool (Mailchimp, Brevo, Google Workspace mail
 *       merge) with your own template. You'd lose the automatic Registered /
 *       Declined tracking, but it can carry far larger lists.
 *     - Add a scheduled backend function (AWS EventBridge + Lambda) that reads
 *       the list itself. That needs a code change to this project.
 *
 * If this file shares a project with google-sheets-sync.gs, that file's
 * onOpen() already builds the "Invites" menu below - don't add another
 * onOpen() here, since only one can exist per project (the second
 * definition would silently replace the first, and you'd risk losing
 * whichever menu isn't in the surviving one). Running this file completely
 * on its own instead? Add this back in:
 *   function onOpen() {
 *     SpreadsheetApp.getUi().createMenu('Invites')
 *       .addItem('Send next batch now', 'sendNextBatch')
 *       .addItem('Reconcile responses now', 'reconcileInviteStatuses')
 *       .addItem('Toggle test mode (ignore 9am-9pm)', 'toggleTestMode')
 *       .addItem('Stop sending (remove trigger)', 'stopSending')
 *       .addToUi();
 *   }
 *
 * Expected sheet: a tab named "Database" with header row containing at
 * least these columns (any order, matched by name):
 *   Alumni Name | Email Address | Contact Number | Status
 *
 * One-time setup:
 *   1. Project Settings (gear icon, left sidebar) > Script Properties > add:
 *        SEND_INVITE_ENDPOINT = the "SEND_INVITE_ENDPOINT" value from your deploy summary
 *                               (https://....lambda-url.<region>.on.aws/)
 *        ADMIN_PASSWORD       = your admin password (the same one you use on /admin)
 *        ADMIN_ENDPOINT       = the "ADMIN_ENDPOINT" value from your deploy summary
 *      (If combined with google-sheets-sync.gs, ADMIN_PASSWORD and
 *      ADMIN_ENDPOINT are almost certainly already set - reuse them, just
 *      add SEND_INVITE_ENDPOINT. ADMIN_ENDPOINT is optional: sending still
 *      works without it, you just lose the reconciliation described below.)
 *   2. Back in the editor, select the "setupInvites" function (top dropdown)
 *      and click Run. Approve the authorization prompt. This installs a
 *      trigger (every SEND_INTERVAL_MINUTES) that sends up to BATCH_SIZE
 *      invites per run, only between BUSINESS_HOURS_START and
 *      BUSINESS_HOURS_END.
 *   3. To stop mid-way (e.g. pause the campaign), run stopSending().
 *
 * Reconciling against what actually happened: clicking "Yes" or "Can't make
 * it" in the invite email never touches this spreadsheet - those write
 * straight to the ticketing site's own database. Left alone, an invited row
 * would sit at "Invite sent <timestamp>" forever even after the person
 * registered or declined - and worse, someone who registers organically
 * (e.g. via the WhatsApp/TinyURL link) before their row's turn in the queue
 * would still get emailed an invite, since sendNextBatch would have no way
 * to know they'd already acted. Every run of sendNextBatch (and the
 * "Reconcile responses now" menu item) calls the same admin endpoint
 * google-sheets-sync.gs uses and rewrites any not-yet-resolved row (blank
 * Status included, not just "Invite sent") to "Registered (<status>)" or
 * "Declined <timestamp>" once a response shows up - this needs ADMIN_ENDPOINT
 * set above; without it, reconciliation is silently skipped and sending is
 * unaffected.
 *
 * Testing outside the 9am-9pm window: "Send next batch now" normally
 * no-ops silently outside those hours (same rule the automatic sending
 * trigger follows), which makes it look broken while you're QAing at
 * 11pm. Run "Invites > Toggle test mode" once to lift that restriction for
 * BOTH the manual menu item and the automatic trigger - it just flips a
 * TEST_MODE Script Property, so it's easy to check ("Toggle test mode"
 * toasts the new state every time) and easy to forget on by accident.
 * Turn it back OFF before your real campaign goes out to the full alumni
 * list, or the pacing this whole file exists for won't apply.
 *
 * Each row's Status cell is updated after processing so re-runs never
 * double-send: "Invite sent <timestamp>", "No email — contact directly"
 * (for blank-email rows - these don't count against the batch limit), or
 * "Error: <message>" - and later, once reconciled, "Registered (<status>)"
 * or "Declined <timestamp>". Rows already starting with "Invite sent",
 * "No email", "Registered", or "Declined" are skipped by future sends.
 */

const DATABASE_SHEET_NAME = 'Database';
const BATCH_SIZE = 12;
// Apps Script's time-based minute trigger only accepts 1, 5, 10, 15, or 30 -
// any other number throws when setupInvites() runs.
const SEND_INTERVAL_MINUTES = 30;
const BUSINESS_HOURS_START = 9;  // 9am
const BUSINESS_HOURS_END = 21;   // 9pm (exclusive)

const COLUMN_ALIASES = {
  name: ['alumni name', 'name'],
  email: ['email address', 'email'],
  phone: ['contact number', 'phone'],
  status: ['status'],
};

function setupInvites() {
  if ([1, 5, 10, 15, 30].indexOf(SEND_INTERVAL_MINUTES) === -1) {
    throw new Error('SEND_INTERVAL_MINUTES must be one of 1, 5, 10, 15, or 30.');
  }
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'sendNextBatch')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('sendNextBatch')
    .timeBased()
    .everyMinutes(SEND_INTERVAL_MINUTES)
    .create();

  // Reconciliation gets its own always-on hourly trigger, separate from the
  // BUSINESS_HOURS-gated sendNextBatch one - responses (someone declining or
  // registering overnight) should show up in the sheet promptly even
  // outside the sending window, not wait until sending resumes at 9am.
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'reconcileInviteStatuses')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('reconcileInviteStatuses')
    .timeBased()
    .everyHours(1)
    .create();

  SpreadsheetApp.getActiveSpreadsheet().toast(
    'Invite sender installed — sends every ' + SEND_INTERVAL_MINUTES + ' min, ' + BATCH_SIZE + ' per run, ' +
    BUSINESS_HOURS_START + ':00–' + BUSINESS_HOURS_END + ':00' +
    (isTestMode() ? ' (test mode is ON - hours are being ignored right now).' : '.') +
    ' Response reconciliation runs hourly around the clock.',
    'Setup complete', 6
  );
}

function stopSending() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'sendNextBatch' || t.getHandlerFunction() === 'reconcileInviteStatuses')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  SpreadsheetApp.getActiveSpreadsheet().toast('Hourly invite-sending and reconciliation triggers removed.', 'Stopped', 5);
}

// TEST_MODE is a Script Property (not a const) specifically so it can be
// flipped from the menu without opening the code - the risk with a code
// constant is someone testing at night, forgetting to flip it back, then
// redeploying it still "on" days later right as the real campaign starts.
function isTestMode() {
  return PropertiesService.getScriptProperties().getProperty('TEST_MODE') === 'true';
}

function toggleTestMode() {
  const props = PropertiesService.getScriptProperties();
  const next = !isTestMode();
  props.setProperty('TEST_MODE', String(next));
  SpreadsheetApp.getActiveSpreadsheet().toast(
    next
      ? 'Test mode ON — "Send next batch now" and the automatic sending trigger will ignore the 9am-9pm window until you toggle this off again.'
      : 'Test mode OFF — sending is back to 9am-9pm only.',
    'Invites', next ? 10 : 5
  );
}

function findColumnIndex(header, aliases) {
  const lower = header.map((h) => String(h || '').trim().toLowerCase());
  for (const alias of aliases) {
    const idx = lower.indexOf(alias);
    if (idx !== -1) return idx;
  }
  return -1;
}

// Rewrites any not-yet-resolved row (blank Status, "Invite sent ...", or a
// stale "Error: ...") to "Registered (...)" or "Declined ..." once the
// ticketing site has a record of that email responding - deliberately not
// limited to rows we've already invited, since someone can organically
// register (e.g. clicking the WhatsApp/TinyURL link directly) before their
// turn in the paced queue ever comes up; without this, sendNextBatch would
// have no way to know and would email them an invite anyway. Never touches
// a blank-email row or one already marked Registered/Declined. Read-only
// against the site (GET, same endpoint google-sheets-sync.gs polls).
// Best-effort: any problem (missing property, network error, bad response)
// just skips reconciliation for this run rather than blocking sends.
function reconcileInviteStatuses() {
  const props = PropertiesService.getScriptProperties();
  const adminEndpoint = props.getProperty('ADMIN_ENDPOINT');
  const adminPassword = props.getProperty('ADMIN_PASSWORD');
  if (!adminEndpoint || !adminPassword) return;

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(DATABASE_SHEET_NAME);
  if (!sheet) return;

  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return;

  const header = values[0];
  const emailCol = findColumnIndex(header, COLUMN_ALIASES.email);
  const statusCol = findColumnIndex(header, COLUMN_ALIASES.status);
  if (emailCol === -1 || statusCol === -1) return;

  const pendingRows = [];
  for (let i = 1; i < values.length; i++) {
    const status = String(values[i][statusCol] || '').trim();
    const email = String(values[i][emailCol] || '').trim();
    if (!email) continue; // nothing to reconcile without an email
    if (status.indexOf('Registered') === 0 || status.indexOf('Declined') === 0) continue; // already resolved
    pendingRows.push(i);
  }
  if (!pendingRows.length) return;

  let items;
  try {
    const res = UrlFetchApp.fetch(adminEndpoint, {
      method: 'get',
      headers: { 'X-Admin-Password': adminPassword },
      muteHttpExceptions: true,
    });
    if (res.getResponseCode() !== 200) return;
    items = JSON.parse(res.getContentText()).items || [];
  } catch (err) {
    return;
  }

  const byEmail = {};
  items.forEach((item) => { byEmail[String(item.email || '').toLowerCase()] = item; });

  let reconciled = 0;
  pendingRows.forEach((i) => {
    const email = String(values[i][emailCol] || '').trim().toLowerCase();
    const match = byEmail[email];
    if (!match) return; // no response yet - leave the "Invite sent" status as-is

    const sheetRow = i + 1;
    if (match.status === 'declined') {
      const when = match.declined_at ? new Date(match.declined_at).toLocaleString() : new Date().toLocaleString();
      sheet.getRange(sheetRow, statusCol + 1).setValue('Declined ' + when);
    } else {
      sheet.getRange(sheetRow, statusCol + 1).setValue('Registered (' + match.status + ')');
    }
    reconciled++;
  });

  if (reconciled > 0) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      'Updated ' + reconciled + ' row(s) with responses.', 'Reconcile complete', 5
    );
  }
}

function sendNextBatch() {
  const testMode = isTestMode();

  // Runs every time, regardless of the hour or test mode - it's a read plus
  // a status-cell update, not a send, so there's no spam-pacing reason to
  // gate it the way actual invite sends are gated below.
  reconcileInviteStatuses();

  const hour = new Date().getHours();
  if (!testMode && (hour < BUSINESS_HOURS_START || hour >= BUSINESS_HOURS_END)) {
    return; // outside the sending window - the trigger will just no-op until 9am
  }

  const props = PropertiesService.getScriptProperties();
  const endpoint = props.getProperty('SEND_INVITE_ENDPOINT');
  const password = props.getProperty('ADMIN_PASSWORD');
  if (!endpoint || !password) {
    throw new Error('Set SEND_INVITE_ENDPOINT and ADMIN_PASSWORD in Project Settings > Script Properties first.');
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(DATABASE_SHEET_NAME);
  if (!sheet) throw new Error('No sheet named "' + DATABASE_SHEET_NAME + '" found.');

  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return; // header only, nothing to send

  const header = values[0];
  const nameCol = findColumnIndex(header, COLUMN_ALIASES.name);
  const emailCol = findColumnIndex(header, COLUMN_ALIASES.email);
  const statusCol = findColumnIndex(header, COLUMN_ALIASES.status);
  if (nameCol === -1 || emailCol === -1 || statusCol === -1) {
    throw new Error('Could not find Alumni Name / Email Address / Status columns in the header row.');
  }

  let sentThisRun = 0;
  for (let i = 1; i < values.length && sentThisRun < BATCH_SIZE; i++) {
    const row = values[i];
    const status = String(row[statusCol] || '').trim();
    if (
      status.indexOf('Invite sent') === 0 ||
      status.indexOf('No email') === 0 ||
      status.indexOf('Registered') === 0 ||
      status.indexOf('Declined') === 0
    ) {
      continue; // already handled in a previous run, or reconciled to a real response
    }

    const name = String(row[nameCol] || '').trim();
    const email = String(row[emailCol] || '').trim();
    const sheetRow = i + 1; // 1-indexed, +1 for header

    if (!email) {
      sheet.getRange(sheetRow, statusCol + 1).setValue('No email — contact directly');
      continue; // doesn't count against the batch limit - it's not a send
    }

    try {
      const res = UrlFetchApp.fetch(endpoint, {
        method: 'post',
        contentType: 'application/json',
        headers: { 'X-Admin-Password': password },
        payload: JSON.stringify({ name: name, email: email }),
        muteHttpExceptions: true,
      });
      if (res.getResponseCode() !== 200) {
        throw new Error('HTTP ' + res.getResponseCode() + ': ' + res.getContentText());
      }
      const data = JSON.parse(res.getContentText());
      if (data.email_warning) {
        sheet.getRange(sheetRow, statusCol + 1).setValue('Error: ' + data.email_warning);
      } else {
        sheet.getRange(sheetRow, statusCol + 1).setValue('Invite sent ' + new Date().toLocaleString());
      }
    } catch (err) {
      sheet.getRange(sheetRow, statusCol + 1).setValue('Error: ' + err.message);
    }

    sentThisRun++;
  }

  if (sentThisRun > 0) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      'Sent ' + sentThisRun + ' invite(s) this run.' + (testMode ? ' (test mode is ON)' : ''),
      'Invite batch complete', 5
    );
  }
}
