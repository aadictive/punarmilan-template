/**
 * Punarmilan - The Reunion — Registrations sync + dashboard
 * Pulls the live registrations table from the ticketing site's admin API
 * into this spreadsheet: a raw "Registrations" tab, plus a "Dashboard" tab
 * with KPI tiles and charts (status breakdown, payment method breakdown,
 * registrations by day). Both are fully rebuilt on every run. Bind this to
 * the Sheet via Extensions > Apps Script.
 *
 * This file can safely share an Apps Script project with invite-mail-merge.gs
 * (e.g. if you want the alumni "Database" tab living in this same
 * spreadsheet) - just add both as separate files under the same project.
 * The one thing that can't be duplicated across files in one project is a
 * top-level function name, which is why setup here is "setupSync" (not
 * "setup") and onOpen() below builds both scripts' menus in one place.
 *
 * One-time setup:
 *   1. Project Settings (gear icon, left sidebar) > Script Properties > add:
 *        ADMIN_ENDPOINT  = the "ADMIN_ENDPOINT" value from your deploy summary
 *                          (https://....lambda-url.<region>.on.aws/)
 *        ADMIN_PASSWORD  = your admin password (the same one you use on /admin)
 *   2. Back in the editor, select the "setupSync" function (top dropdown)
 *      and click Run. Google will ask you to authorize the script (it only
 *      talks to the admin endpoint and this spreadsheet) - approve it.
 *      This creates both tabs, syncs once, and installs a time-based
 *      trigger so it keeps syncing automatically from then on.
 *
 * To change how often it syncs, edit SYNC_INTERVAL_MINUTES below and re-run
 * setupSync() once (it replaces the old trigger). Apps Script's time-based
 * trigger only accepts 1, 5, 10, 15, or 30 as the interval - any other
 * number throws an error.
 */

const SHEET_NAME = 'Registrations';
const DASHBOARD_SHEET_NAME = 'Dashboard';
const SYNC_INTERVAL_MINUTES = 1;

const COLUMNS = [
  ['name', 'Name'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['batch', 'Batch'],
  ['college', 'College'],
  ['quantity', 'Qty'],
  ['amount_cents', 'Amount'],
  ['status', 'Status'],
  ['payment_method', 'Confirmed via'],
  ['selected_payment_method', 'Intends to pay via'],
  ['ticket_code', 'Code'],
  ['checked_in', 'Checked in?'],
  ['checked_in_at', 'Checked in at'],
  ['volunteer', 'Volunteer?'],
  ['expectations', 'Looking forward to'],
  ['created_at', 'Submitted'],
  ['prior_history', 'Prior history'],
];

// Somaiya site palette, reused here so the dashboard matches the ticketing site.
const COLORS = {
  ink: '#1B2A4A',
  inkSoft: '#445070',
  maroon: '#7A2E2E',
  gold: '#B08D3E',
  paper: '#F1ECE1',
  white: '#FFFDF9',
  line: '#D9D0BC',
  green: '#4C8254',
};

function setupSync() {
  syncRegistrations();
  installTrigger();
}

function installTrigger() {
  if ([1, 5, 10, 15, 30].indexOf(SYNC_INTERVAL_MINUTES) === -1) {
    throw new Error('SYNC_INTERVAL_MINUTES must be one of 1, 5, 10, 15, or 30.');
  }
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'syncRegistrations')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('syncRegistrations')
    .timeBased()
    .everyMinutes(SYNC_INTERVAL_MINUTES)
    .create();
}

// Builds the custom menu(s) for this spreadsheet. If invite-mail-merge.gs
// lives in this same project, its menu is added here too (rather than
// each file defining its own onOpen()) since only one onOpen() can exist
// per project - see typeof guard below, which no-ops harmlessly if that
// file isn't present.
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('Registrations')
    .addItem('Sync now', 'syncRegistrations')
    .addToUi();
  if (typeof sendNextBatch === 'function') {
    ui.createMenu('Invites')
      .addItem('Send next batch now', 'sendNextBatch')
      .addItem('Reconcile responses now', 'reconcileInviteStatuses')
      .addItem('Toggle test mode (ignore 9am-9pm)', 'toggleTestMode')
      .addItem('Stop sending (remove hourly trigger)', 'stopSending')
      .addToUi();
  }
}

function syncRegistrations() {
  const props = PropertiesService.getScriptProperties();
  const endpoint = props.getProperty('ADMIN_ENDPOINT');
  const password = props.getProperty('ADMIN_PASSWORD');
  if (!endpoint || !password) {
    throw new Error('Set ADMIN_ENDPOINT and ADMIN_PASSWORD in Project Settings > Script Properties first.');
  }

  const res = UrlFetchApp.fetch(endpoint, {
    method: 'get',
    headers: { 'X-Admin-Password': password },
    muteHttpExceptions: true,
  });
  if (res.getResponseCode() !== 200) {
    throw new Error('Admin endpoint returned ' + res.getResponseCode() + ': ' + res.getContentText());
  }

  const data = JSON.parse(res.getContentText());
  const items = data.items || [];

  writeRegistrationsSheet(items);
  writeDashboardSheet(items);

  const summary =
    data.count + ' registrations · ' + data.paid_count + ' paid · $' +
    (Number(data.total_collected_cents || 0) / 100).toFixed(2) + ' collected · ' +
    (data.checked_in_count || 0) + ' checked in · last synced ' + new Date().toLocaleString();
  SpreadsheetApp.getActiveSpreadsheet().toast(summary, 'Registrations synced', 5);
}

function writeRegistrationsSheet(items) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(SHEET_NAME);
  // clearContents() only wipes values, not background/font color - if the
  // row count ever shrinks between syncs, leftover rows below the new data
  // would keep their old color forever. clear() wipes both.
  sheet.clear();

  const header = COLUMNS.map((c) => c[1]);
  const rows = items.map((item) =>
    COLUMNS.map(([key]) => {
      const v = item[key];
      if (key === 'amount_cents') return (Number(v || 0) / 100).toFixed(2);
      if (key === 'checked_in' || key === 'volunteer') return v ? 'Yes' : 'No';
      if (key === 'expectations') return Array.isArray(v) ? v.join(', ') : '';
      if (key === 'phone') return v ? (item.country_code || '+1') + ' ' + v : '';
      if (key === 'prior_history') {
        // Re-registering (or declining) after a refund carries that history
        // forward server-side rather than losing it - this column is where
        // it actually surfaces here, since the row itself just looks like a
        // fresh registration otherwise (same as it does in the admin panel's
        // expandable row detail).
        const parts = [];
        if (item.previously_refunded_at) {
          parts.push(
            'Refunded ' + new Date(item.previously_refunded_at).toLocaleString() +
            (item.previously_refunded_ticket_code ? ' (ref ' + item.previously_refunded_ticket_code + ')' : '') +
            (item.refund_count > 1 ? ' — ' + item.refund_count + 'x total' : '')
          );
        }
        if (item.previously_declined_at) {
          parts.push('Declined ' + new Date(item.previously_declined_at).toLocaleString());
        }
        return parts.join(' | ');
      }
      return v == null ? '' : v;
    })
  );

  sheet.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  if (rows.length) {
    const dataRange = sheet.getRange(2, 1, rows.length, header.length);
    dataRange.setValues(rows);

    // Color each row by status - checked-in wins over paid (a checked-in
    // person is always paid too, but "they're here" is the more useful signal).
    const backgrounds = items.map((item) => {
      const color = statusRowColor(item);
      return new Array(header.length).fill(color.bg);
    });
    const fontColors = items.map((item) => {
      const color = statusRowColor(item);
      return new Array(header.length).fill(color.font);
    });
    dataRange.setBackgrounds(backgrounds);
    dataRange.setFontColors(fontColors);
  }
  sheet.autoResizeColumns(1, header.length);
}

// Row-color rule for the Registrations tab. Order matters - refunded (bright
// red) is checked first since it's the most important thing to notice even
// if the row was also checked-in at some point; checked-in (dark green)
// otherwise takes priority over paid (light green) since it's the more
// useful signal on the day of the event.
const ROW_COLORS = {
  refunded: { bg: '#E53935', font: '#FFFFFF' },    // bright red
  checkedIn: { bg: '#2E7D32', font: '#FFFFFF' },   // dark green
  paid: { bg: '#C8E6C9', font: null },             // light green
  viewedOnly: { bg: '#FFD9A8', font: null },       // orange
  pending: { bg: '#FFF3B0', font: null },          // yellow
  declined: { bg: '#E0E0E0', font: '#616161' },    // neutral gray
  none: { bg: null, font: null },
};

function statusRowColor(item) {
  if (item.status === 'refunded') return ROW_COLORS.refunded;
  if (item.checked_in) return ROW_COLORS.checkedIn;
  if (item.status === 'paid') return ROW_COLORS.paid;
  if (item.status === 'viewed_price') return ROW_COLORS.viewedOnly;
  if (item.status === 'pending_payment') return ROW_COLORS.pending;
  if (item.status === 'declined') return ROW_COLORS.declined;
  return ROW_COLORS.none;
}

// --- Dashboard: KPI tiles + charts, fully rebuilt every sync -------------

function writeDashboardSheet(items) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(DASHBOARD_SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(DASHBOARD_SHEET_NAME);

  // Remove old charts first - they're separate objects, not cleared by clear().
  sheet.getCharts().forEach((c) => sheet.removeChart(c));
  sheet.clear();

  const paidItems = items.filter((i) => i.status === 'paid');
  const kpis = {
    total: items.length,
    paid: paidItems.length,
    pending: items.filter((i) => i.status === 'pending_payment').length,
    viewedOnly: items.filter((i) => i.status === 'viewed_price').length,
    checkedIn: items.filter((i) => i.checked_in).length,
    refunded: items.filter((i) => i.status === 'refunded').length,
    declined: items.filter((i) => i.status === 'declined').length,
    collected: '$' + (paidItems.reduce((sum, i) => sum + Number(i.amount_cents || 0), 0) / 100).toFixed(2),
  };

  writeKpiTiles(sheet, kpis);
  writeStatusChart(sheet, kpis);
  writeMethodChart(sheet, paidItems);
  writeDailyChart(sheet, items);

  sheet.setColumnWidth(1, 130);
  for (let c = 2; c <= 16; c++) sheet.setColumnWidth(c, 90);
  sheet.setHiddenGridlines(true);
}

const KPI_TILES = [
  { label: 'Registrations', key: 'total' },
  { label: 'Paid', key: 'paid' },
  { label: 'Pending Payment', key: 'pending' },
  { label: 'Viewed Price Only', key: 'viewedOnly' },
  { label: 'Checked In', key: 'checkedIn' },
  { label: 'Refunded', key: 'refunded', color: '#E53935' }, // matches the row-color red
  { label: 'Declined', key: 'declined', color: '#757575' }, // matches the row-color gray
  { label: 'Collected', key: 'collected' },
];

function writeKpiTiles(sheet, kpis) {
  KPI_TILES.forEach((tile, i) => {
    const startCol = i * 2 + 1;
    sheet.getRange(1, startCol, 1, 2).merge()
      .setValue(tile.label)
      .setFontSize(10).setFontColor(COLORS.inkSoft).setFontWeight('bold')
      .setHorizontalAlignment('center').setVerticalAlignment('middle')
      .setBackground(COLORS.paper);
    sheet.getRange(2, startCol, 1, 2).merge()
      .setValue(kpis[tile.key])
      .setFontSize(22).setFontWeight('bold').setFontColor(tile.color || COLORS.maroon)
      .setHorizontalAlignment('center').setVerticalAlignment('middle')
      .setBackground(COLORS.white)
      .setBorder(true, true, true, true, false, false, COLORS.line, SpreadsheetApp.BorderStyle.SOLID);
  });
  sheet.setRowHeight(1, 24);
  sheet.setRowHeight(2, 44);
  sheet.setRowHeight(3, 14);
}

function writeStatusChart(sheet, kpis) {
  // Helper data table, tucked out to the right of the visible dashboard area
  // (past all 8 KPI tiles, which now span columns 1-16).
  const anchorRow = 5, dataCol = 19; // column S
  const rows = [
    ['Status', 'Count'],
    ['Paid', kpis.paid],
    ['Pending payment', kpis.pending],
    ['Viewed price only', kpis.viewedOnly],
    ['Refunded', kpis.refunded],
    ['Declined', kpis.declined],
  ];
  sheet.getRange(anchorRow, dataCol, rows.length, 2).setValues(rows);
  const dataRange = sheet.getRange(anchorRow, dataCol, rows.length, 2);

  const chart = sheet.newChart()
    .setChartType(Charts.ChartType.PIE)
    .addRange(dataRange)
    .setPosition(4, 1, 0, 0)
    .setOption('title', 'Registration status')
    .setOption('pieHole', 0.4)
    .setOption('colors', ['#66BB6A', '#FBC02D', '#FB8C00', '#E53935', '#9E9E9E'])
    .setOption('width', 400)
    .setOption('height', 280)
    .setOption('legend', { position: 'right' })
    .build();
  sheet.insertChart(chart);
}

function writeMethodChart(sheet, paidItems) {
  const counts = {};
  paidItems.forEach((i) => {
    const m = i.payment_method || 'unknown';
    counts[m] = (counts[m] || 0) + 1;
  });
  const anchorRow = 12, dataCol = 19;
  const rows = [['Method', 'Count']].concat(
    Object.keys(counts).length ? Object.keys(counts).map((k) => [k, counts[k]]) : [['No paid registrations yet', 0]]
  );
  sheet.getRange(anchorRow, dataCol, rows.length, 2).setValues(rows);
  const dataRange = sheet.getRange(anchorRow, dataCol, rows.length, 2);

  const chart = sheet.newChart()
    .setChartType(Charts.ChartType.PIE)
    .addRange(dataRange)
    .setPosition(4, 8, 0, 0)
    .setOption('title', 'How paid registrations paid')
    .setOption('pieHole', 0.4)
    .setOption('colors', [COLORS.ink, COLORS.gold, COLORS.maroon, COLORS.green])
    .setOption('width', 400)
    .setOption('height', 280)
    .setOption('legend', { position: 'right' })
    .build();
  sheet.insertChart(chart);
}

function writeDailyChart(sheet, items) {
  const byDay = {};
  items.forEach((i) => {
    if (!i.created_at) return;
    const day = String(i.created_at).slice(0, 10); // "2026-09-06T..." -> "2026-09-06"
    byDay[day] = (byDay[day] || 0) + 1;
  });
  const days = Object.keys(byDay).sort();
  const anchorRow = 20, dataCol = 19;
  const rows = [['Date', 'Registrations']].concat(
    days.length ? days.map((d) => [d, byDay[d]]) : [['No data yet', 0]]
  );
  sheet.getRange(anchorRow, dataCol, rows.length, 2).setValues(rows);
  const dataRange = sheet.getRange(anchorRow, dataCol, rows.length, 2);

  const chart = sheet.newChart()
    .setChartType(Charts.ChartType.COLUMN)
    .addRange(dataRange)
    .setPosition(19, 1, 0, 0)
    .setOption('title', 'Registrations by day')
    .setOption('colors', [COLORS.maroon])
    .setOption('width', 820)
    .setOption('height', 280)
    .setOption('legend', { position: 'none' })
    .build();
  sheet.insertChart(chart);
}
