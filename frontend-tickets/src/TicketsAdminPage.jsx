import { Fragment, useMemo, useState } from 'react'
import './TicketsAdminPage.css'

const ADMIN_ENDPOINT = import.meta.env.VITE_ADMIN_ENDPOINT || 'https://REPLACE-WITH-YOUR-ADMIN-LAMBDA-URL'
const MARK_PAID_ENDPOINT = import.meta.env.VITE_MARK_PAID_ENDPOINT || 'https://REPLACE-WITH-YOUR-MARK-PAID-LAMBDA-URL'
const UNMARK_PAID_ENDPOINT = import.meta.env.VITE_UNMARK_PAID_ENDPOINT || 'https://REPLACE-WITH-YOUR-UNMARK-PAID-LAMBDA-URL'
const SEND_REMINDER_ENDPOINT = import.meta.env.VITE_SEND_REMINDER_ENDPOINT || 'https://REPLACE-WITH-YOUR-SEND-REMINDER-LAMBDA-URL'
const ADMIN_CHECKIN_ENDPOINT = import.meta.env.VITE_ADMIN_CHECKIN_ENDPOINT || 'https://REPLACE-WITH-YOUR-ADMIN-CHECKIN-LAMBDA-URL'
const ADMIN_SEND_EMAIL_ENDPOINT = import.meta.env.VITE_ADMIN_SEND_EMAIL_ENDPOINT || 'https://REPLACE-WITH-YOUR-ADMIN-SEND-EMAIL-LAMBDA-URL'

const EMAIL_TEMPLATES = [
  {
    key: 'payment_reminder',
    label: 'Payment reminder',
    description: "Nudges someone who hasn't paid yet - leads with whichever method they picked (Venmo/Zelle/card), or a card link if they haven't picked one.",
    eligible: (item) => item.status !== 'paid' && item.status !== 'refunded' && item.status !== 'declined',
    ineligibleReason: 'already paid, refunded, or declined',
  },
  {
    key: 'confirmation',
    label: 'Resend confirmation',
    description: 'Re-sends the e-ticket confirmation email (with QR code) to someone already marked paid.',
    eligible: (item) => item.status === 'paid',
    ineligibleReason: 'not marked paid',
  },
  {
    key: 'event_reminder',
    label: 'Event reminder (tomorrow)',
    description: '"See you tomorrow" email with the e-ticket QR again, for already-paid attendees.',
    eligible: (item) => item.status === 'paid',
    ineligibleReason: 'not marked paid',
  },
]

const STATUS_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'paid', label: 'Paid' },
  { key: 'pending_payment', label: 'Pending' },
  { key: 'viewed_price', label: 'Viewed only' },
  { key: 'refunded', label: 'Refunded' },
  { key: 'declined', label: 'Declined' },
]

function formatDollars(cents) {
  return `$${((cents || 0) / 100).toFixed(2)}`
}

function BarChart({ rows, colorFor }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <div>
      {rows.map((r) => (
        <div className="bar-row" key={r.label}>
          <span className="bar-label">{r.label}</span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${(r.count / max) * 100}%`, background: colorFor(r.label) }}
            />
          </div>
          <span className="bar-count">{r.count}</span>
        </div>
      ))}
    </div>
  )
}

export default function TicketsAdminPage() {
  const [password, setPassword] = useState('')
  const [role, setRole] = useState(null) // 'admin' | 'view_only'
  const [authed, setAuthed] = useState(false)
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('idle') // idle | loading | error
  const [errorMsg, setErrorMsg] = useState('')
  const [markingEmail, setMarkingEmail] = useState('')
  const [remindingEmail, setRemindingEmail] = useState('')
  const [checkinEmail, setCheckinEmail] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [volunteerOnly, setVolunteerOnly] = useState(false)
  const [showDeclined, setShowDeclined] = useState(false)
  const [expandedEmail, setExpandedEmail] = useState(null)
  const [tab, setTab] = useState('registrations') // registrations | stats | emails
  const [emailSearch, setEmailSearch] = useState('')
  const [emailStatusFilter, setEmailStatusFilter] = useState('all')
  const [emailVolunteerOnly, setEmailVolunteerOnly] = useState(false)
  const [selectedEmails, setSelectedEmails] = useState(() => new Set())
  const [emailTemplate, setEmailTemplate] = useState('payment_reminder')
  const [sending, setSending] = useState(false)
  const [sendProgress, setSendProgress] = useState('')
  const [sendResult, setSendResult] = useState(null)

  async function fetchData(pw) {
    setStatus('loading')
    setErrorMsg('')
    try {
      const res = await fetch(ADMIN_ENDPOINT, {
        headers: { 'X-Admin-Password': pw },
      })
      if (res.status === 401) throw new Error('Incorrect password.')
      if (!res.ok) throw new Error('Something went wrong loading registrations.')
      const json = await res.json()
      // The server says which password this was; the UI never guesses.
      setRole(json.role === 'admin' ? 'admin' : 'view_only')
      setData(json)
      setAuthed(true)
      setStatus('idle')
    } catch (err) {
      setStatus('error')
      setErrorMsg(err.message)
    }
  }

  function handleLogin(e) {
    e.preventDefault()
    fetchData(password)
  }

  const isViewOnly = role !== 'admin'

  function handleExportCsv() {
    fetch(`${ADMIN_ENDPOINT}?format=csv`, { headers: { 'X-Admin-Password': password } })
      .then((res) => res.text())
      .then((csv) => {
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'tickets.csv'
        a.click()
        URL.revokeObjectURL(url)
      })
  }

  async function handleMarkPaid(email) {
    if (isViewOnly) return
    if (!window.confirm(`Mark ${email} as paid?`)) return
    setMarkingEmail(email)
    setErrorMsg('')
    try {
      const res = await fetch(MARK_PAID_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Password': password },
        body: JSON.stringify({ email }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || 'Failed to mark as paid.')
      await fetchData(password)
      if (data.email_warning) setErrorMsg(data.email_warning)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setMarkingEmail('')
    }
  }

  async function handleUnmarkPaid(email) {
    if (isViewOnly) return
    if (!window.confirm(`Undo "paid" for ${email}? They will not be re-notified.`)) return
    setMarkingEmail(email)
    setErrorMsg('')
    try {
      const res = await fetch(UNMARK_PAID_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Password': password },
        body: JSON.stringify({ email }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || 'Failed to unmark as paid.')
      await fetchData(password)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setMarkingEmail('')
    }
  }

  async function handleRefund(email) {
    if (isViewOnly) return
    if (!window.confirm(`Mark ${email} as refunded and email them a confirmation? Process the actual refund in Stripe/Venmo/Zelle yourself first - this only updates the record.`)) return
    setMarkingEmail(email)
    setErrorMsg('')
    try {
      const res = await fetch(UNMARK_PAID_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Password': password },
        body: JSON.stringify({ email, target_status: 'refunded' }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || 'Failed to mark as refunded.')
      await fetchData(password)
      if (data.email_warning) setErrorMsg(data.email_warning)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setMarkingEmail('')
    }
  }

  async function handleSendReminder(email) {
    if (isViewOnly) return
    if (!window.confirm(`Send a payment reminder to ${email}?`)) return
    setRemindingEmail(email)
    setErrorMsg('')
    try {
      const res = await fetch(SEND_REMINDER_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Password': password },
        body: JSON.stringify({ email }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || 'Failed to send reminder.')
      if (data.email_warning) setErrorMsg(data.email_warning)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setRemindingEmail('')
    }
  }

  async function handleToggleCheckin(email, nextValue) {
    if (isViewOnly) return
    const verb = nextValue ? 'Check in' : 'Undo check-in for'
    if (!window.confirm(`${verb} ${email}?`)) return
    setCheckinEmail(email)
    setErrorMsg('')
    try {
      const res = await fetch(ADMIN_CHECKIN_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Password': password },
        body: JSON.stringify({ email, checked_in: nextValue }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || 'Failed to update check-in status.')
      await fetchData(password)
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setCheckinEmail('')
    }
  }

  const q = search.trim().toLowerCase()
  const filteredItems = useMemo(() => {
    if (!data) return []
    return data.items.filter((item) => {
      if (item.status === 'declined' && !showDeclined && statusFilter !== 'declined') return false
      if (statusFilter !== 'all' && item.status !== statusFilter) return false
      if (volunteerOnly && !item.volunteer) return false
      if (!q) return true
      return (
        (item.name || '').toLowerCase().includes(q) ||
        (item.ticket_code || '').toLowerCase().includes(q) ||
        (item.email || '').toLowerCase().includes(q)
      )
    })
  }, [data, statusFilter, volunteerOnly, showDeclined, q])

  const statusCounts = useMemo(() => {
    if (!data) return {}
    const counts = { all: data.items.length, volunteer: 0 }
    for (const item of data.items) {
      counts[item.status] = (counts[item.status] || 0) + 1
      if (item.volunteer) counts.volunteer += 1
    }
    return counts
  }, [data])

  const stats = useMemo(() => {
    if (!data) return null
    const pending = data.items.filter((i) => i.status === 'pending_payment').length
    const viewedOnly = data.items.filter((i) => i.status === 'viewed_price').length
    const methodCounts = {}
    for (const item of data.items) {
      if (item.status !== 'paid') continue
      const m = item.payment_method || 'unknown'
      methodCounts[m] = (methodCounts[m] || 0) + 1
    }
    return {
      total: data.count,
      paid: data.paid_count,
      pending,
      viewedOnly,
      checkedIn: data.checked_in_count || 0,
      refunded: data.refunded_count || 0,
      declined: data.declined_count || 0,
      collectedCents: data.total_collected_cents,
      methodCounts,
    }
  }, [data])

  const emailQ = emailSearch.trim().toLowerCase()
  const emailFilteredItems = useMemo(() => {
    if (!data) return []
    return data.items.filter((item) => {
      if (item.status === 'declined' && !showDeclined && emailStatusFilter !== 'declined') return false
      if (emailStatusFilter !== 'all' && item.status !== emailStatusFilter) return false
      if (emailVolunteerOnly && !item.volunteer) return false
      if (!emailQ) return true
      return (
        (item.name || '').toLowerCase().includes(emailQ) ||
        (item.ticket_code || '').toLowerCase().includes(emailQ) ||
        (item.email || '').toLowerCase().includes(emailQ)
      )
    })
  }, [data, emailStatusFilter, emailVolunteerOnly, showDeclined, emailQ])

  const activeTemplate = EMAIL_TEMPLATES.find((t) => t.key === emailTemplate)
  const selectedItems = data ? data.items.filter((i) => selectedEmails.has(i.email)) : []
  const eligibleSelectedCount = activeTemplate ? selectedItems.filter(activeTemplate.eligible).length : 0
  const allVisibleSelected = emailFilteredItems.length > 0 && emailFilteredItems.every((i) => selectedEmails.has(i.email))

  function toggleEmailSelected(email) {
    setSelectedEmails((prev) => {
      const next = new Set(prev)
      if (next.has(email)) next.delete(email)
      else next.add(email)
      return next
    })
  }

  function toggleSelectAllVisible() {
    setSelectedEmails((prev) => {
      const next = new Set(prev)
      if (allVisibleSelected) {
        emailFilteredItems.forEach((i) => next.delete(i.email))
      } else {
        emailFilteredItems.forEach((i) => next.add(i.email))
      }
      return next
    })
  }

  async function handleBulkSend() {
    if (isViewOnly || !activeTemplate) return
    const eligible = selectedItems.filter(activeTemplate.eligible)
    const skipped = selectedItems.length - eligible.length
    if (eligible.length === 0) {
      window.alert(`None of the selected registrations are eligible for "${activeTemplate.label}" (${activeTemplate.ineligibleReason}).`)
      return
    }
    if (!window.confirm(
      `Send "${activeTemplate.label}" to ${eligible.length} recipient${eligible.length === 1 ? '' : 's'}` +
      (skipped ? ` (${skipped} of your selection skipped: ${activeTemplate.ineligibleReason})` : '') + '?'
    )) return

    setSending(true)
    setSendResult(null)
    setErrorMsg('')
    let sent = 0
    let failed = 0
    for (let i = 0; i < eligible.length; i++) {
      const item = eligible[i]
      setSendProgress(`Sending ${i + 1} of ${eligible.length}…`)
      try {
        const endpoint = emailTemplate === 'payment_reminder' ? SEND_REMINDER_ENDPOINT : ADMIN_SEND_EMAIL_ENDPOINT
        const body = emailTemplate === 'payment_reminder' ? { email: item.email } : { email: item.email, template: emailTemplate }
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Admin-Password': password },
          body: JSON.stringify(body),
        })
        const resData = await res.json().catch(() => ({}))
        if (!res.ok || resData.email_warning) failed += 1
        else sent += 1
      } catch {
        failed += 1
      }
    }
    setSending(false)
    setSendProgress('')
    setSendResult({ sent, failed, skipped, template: activeTemplate.label })
    await fetchData(password)
  }

  if (!authed) {
    return (
      <main className="admin-page">
        <form className="login-card" onSubmit={handleLogin}>
          <h1 className="admin-title">Tickets Admin</h1>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              autoFocus
            />
          </label>
          {status === 'error' && <p className="error-text">{errorMsg}</p>}
          <button type="submit" className="submit-btn" disabled={status === 'loading'}>
            {status === 'loading' ? 'Checking…' : 'View registrations'}
          </button>
        </form>
      </main>
    )
  }

  return (
    <main className="admin-page wide">
      <div className="admin-header">
        <div className="admin-header-left">
          <h1 className="admin-title compact">Tickets Admin</h1>
          <span className={`role-badge${isViewOnly ? ' view-only' : ''}`}>
            {isViewOnly ? 'View only' : 'Full access'}
          </span>
          <div className="admin-tabs">
            <button
              className={`admin-tab-btn${tab === 'registrations' ? ' active' : ''}`}
              onClick={() => setTab('registrations')}
            >
              Registrations
            </button>
            <button
              className={`admin-tab-btn${tab === 'stats' ? ' active' : ''}`}
              onClick={() => setTab('stats')}
            >
              Stats
            </button>
            <button
              className={`admin-tab-btn${tab === 'emails' ? ' active' : ''}`}
              onClick={() => setTab('emails')}
            >
              Emails
            </button>
          </div>
        </div>
        <div className="admin-actions">
          <button className="secondary-btn" onClick={() => fetchData(password)}>Refresh</button>
          <button className="submit-btn" onClick={handleExportCsv}>Export CSV</button>
        </div>
      </div>

      {errorMsg && <p className="error-text">{errorMsg}</p>}

      {tab === 'stats' ? (
        <>
          <p className="stats-note">
            Kept on a separate tab so collected-amount figures aren't visible if this screen is
            shared or shown to someone else by accident.
          </p>
          <div className="stats-grid">
            <div className="stat-card">
              <p className="stat-label">Interests</p>
              <p className="stat-value">{stats.total}</p>
            </div>
            <div className="stat-card accent-green">
              <p className="stat-label">Paid</p>
              <p className="stat-value">{stats.paid}</p>
            </div>
            <div className="stat-card accent-gold">
              <p className="stat-label">Pending Payment</p>
              <p className="stat-value">{stats.pending}</p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Viewed Price Only</p>
              <p className="stat-value">{stats.viewedOnly}</p>
            </div>
            <div className="stat-card accent-green">
              <p className="stat-label">Checked In</p>
              <p className="stat-value">{stats.checkedIn}</p>
            </div>
            <div className="stat-card accent-red">
              <p className="stat-label">Refunded</p>
              <p className="stat-value">{stats.refunded}</p>
            </div>
            <div className="stat-card accent-gray">
              <p className="stat-label">Declined</p>
              <p className="stat-value">{stats.declined}</p>
            </div>
            <div className="stat-card">
              <p className="stat-label">Collected</p>
              <p className="stat-value">{formatDollars(stats.collectedCents)}</p>
            </div>
          </div>

          <div className="charts-row">
            <div className="chart-card">
              <h3>Registration status</h3>
              <BarChart
                rows={[
                  { label: 'Paid', count: stats.paid },
                  { label: 'Pending payment', count: stats.pending },
                  { label: 'Viewed price only', count: stats.viewedOnly },
                  { label: 'Refunded', count: stats.refunded },
                  { label: 'Declined', count: stats.declined },
                ]}
                colorFor={(label) => ({
                  Paid: '#66BB6A',
                  'Pending payment': '#FBC02D',
                  'Viewed price only': '#FB8C00',
                  Refunded: '#E53935',
                  Declined: '#9E9E9E',
                }[label] || 'var(--ink-soft)')}
              />
            </div>
            <div className="chart-card">
              <h3>How paid registrations paid</h3>
              {Object.keys(stats.methodCounts).length ? (
                <BarChart
                  rows={Object.entries(stats.methodCounts).map(([label, count]) => ({ label, count }))}
                  colorFor={() => 'var(--maroon)'}
                />
              ) : (
                <p className="stats-note" style={{ margin: 0 }}>No paid registrations yet.</p>
              )}
            </div>
          </div>
        </>
      ) : tab === 'emails' ? (
        <>
          <div className="admin-filters">
            <input
              type="text"
              className="admin-search"
              placeholder="Search by name, email, or reference code…"
              value={emailSearch}
              onChange={(e) => setEmailSearch(e.target.value)}
            />
            <div className="filter-chips">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={`filter-chip${emailStatusFilter === f.key ? ' active' : ''}`}
                  onClick={() => setEmailStatusFilter(f.key)}
                >
                  {f.label} ({statusCounts[f.key] || 0})
                </button>
              ))}
              <button
                className={`filter-chip${emailVolunteerOnly ? ' active' : ''}`}
                onClick={() => setEmailVolunteerOnly((v) => !v)}
              >
                Ready to volunteer ({statusCounts.volunteer || 0})
              </button>
              <label className="filter-chip checkbox-chip">
                <input
                  type="checkbox"
                  checked={showDeclined}
                  onChange={(e) => setShowDeclined(e.target.checked)}
                />
                Show declined
              </label>
            </div>
          </div>

          <div className="email-toolbar">
            <div className="template-picker">
              {EMAIL_TEMPLATES.map((t) => (
                <label key={t.key} className={`template-option${emailTemplate === t.key ? ' active' : ''}`}>
                  <input
                    type="radio"
                    name="emailTemplate"
                    checked={emailTemplate === t.key}
                    onChange={() => setEmailTemplate(t.key)}
                  />
                  <span>
                    <strong>{t.label}</strong>
                    <small>{t.description}</small>
                  </span>
                </label>
              ))}
            </div>
            <div className="email-send-col">
              <button
                className="submit-btn"
                disabled={isViewOnly || sending || selectedEmails.size === 0}
                title={isViewOnly ? 'View-only login' : undefined}
                onClick={handleBulkSend}
              >
                {sending
                  ? sendProgress || 'Sending…'
                  : `Send "${activeTemplate.label}" to ${selectedEmails.size} selected`}
              </button>
              {selectedEmails.size > 0 && !sending && (
                <p className="email-eligible-note">
                  {eligibleSelectedCount} of {selectedEmails.size} selected are eligible for this template.
                </p>
              )}
              {sendResult && (
                <p className="email-eligible-note">
                  "{sendResult.template}": sent {sendResult.sent}, failed {sendResult.failed}
                  {sendResult.skipped ? `, skipped ${sendResult.skipped} (ineligible)` : ''}.
                </p>
              )}
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>
                    <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAllVisible} />
                  </th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Intends to pay via</th>
                  <th>Volunteer?</th>
                </tr>
              </thead>
              <tbody>
                {emailFilteredItems.map((item) => (
                  <tr key={item.email} className="row-main" onClick={() => toggleEmailSelected(item.email)}>
                    <td onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedEmails.has(item.email)}
                        onChange={() => toggleEmailSelected(item.email)}
                      />
                    </td>
                    <td className="name-cell">{item.name}</td>
                    <td>{item.email}</td>
                    <td>
                      <span className={`status-pill status-${item.status}`}>{item.status}</span>
                    </td>
                    <td>{item.selected_payment_method || '—'}</td>
                    <td>{item.volunteer ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.items.length === 0 && <p className="empty-state">No registrations yet.</p>}
            {data.items.length > 0 && emailFilteredItems.length === 0 && (
              <p className="empty-state">No registrations match the current search/filter.</p>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="admin-filters">
            <input
              type="text"
              className="admin-search"
              placeholder="Search by name, email, or reference code…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="filter-chips">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={`filter-chip${statusFilter === f.key ? ' active' : ''}`}
                  onClick={() => setStatusFilter(f.key)}
                >
                  {f.label} ({statusCounts[f.key] || 0})
                </button>
              ))}
              <button
                className={`filter-chip${volunteerOnly ? ' active' : ''}`}
                onClick={() => setVolunteerOnly((v) => !v)}
              >
                Ready to volunteer ({statusCounts.volunteer || 0})
              </button>
              <label className="filter-chip checkbox-chip">
                <input
                  type="checkbox"
                  checked={showDeclined}
                  onChange={(e) => setShowDeclined(e.target.checked)}
                />
                Show declined
              </label>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Amount</th>
                  <th>Code</th>
                  <th>Checked in</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item) => {
                  const isExpanded = expandedEmail === item.email
                  return (
                    <Fragment key={item.email}>
                      <tr
                        className={`row-main${isExpanded ? ' expanded' : ''}`}
                        onClick={() => setExpandedEmail(isExpanded ? null : item.email)}
                      >
                        <td><span className="expand-icon">▶</span></td>
                        <td className="name-cell">{item.name}</td>
                        <td>{item.email}</td>
                        <td>
                          <span className={`status-pill status-${item.status}`}>{item.status}</span>
                        </td>
                        <td>{formatDollars(item.amount_cents)}</td>
                        <td>{item.ticket_code}</td>
                        <td>
                          <span className={`checked-in-pill ${item.checked_in ? 'yes' : 'no'}`}>
                            {item.checked_in ? `Yes, ${new Date(item.checked_in_at).toLocaleTimeString()}` : 'No'}
                          </span>
                        </td>
                        <td className="action-cell" onClick={(e) => e.stopPropagation()}>
                          {item.status === 'paid' && (
                            <>
                              <button
                                className="secondary-btn small-btn"
                                disabled={isViewOnly || markingEmail === item.email}
                                title={isViewOnly ? 'View-only login' : undefined}
                                onClick={() => handleUnmarkPaid(item.email)}
                              >
                                {markingEmail === item.email ? '…' : 'Unmark paid'}
                              </button>
                              <button
                                className="secondary-btn small-btn"
                                disabled={isViewOnly || markingEmail === item.email}
                                title={isViewOnly ? 'View-only login' : undefined}
                                onClick={() => handleRefund(item.email)}
                              >
                                {markingEmail === item.email ? '…' : 'Refund'}
                              </button>
                            </>
                          )}
                          {item.status !== 'paid' && item.status !== 'refunded' && item.status !== 'declined' && (
                            <>
                              <button
                                className="secondary-btn small-btn"
                                disabled={isViewOnly || markingEmail === item.email}
                                title={isViewOnly ? 'View-only login' : undefined}
                                onClick={() => handleMarkPaid(item.email)}
                              >
                                {markingEmail === item.email ? '…' : 'Mark paid'}
                              </button>
                              <button
                                className="secondary-btn small-btn"
                                disabled={isViewOnly || remindingEmail === item.email}
                                title={isViewOnly ? 'View-only login' : undefined}
                                onClick={() => handleSendReminder(item.email)}
                              >
                                {remindingEmail === item.email ? '…' : 'Send reminder'}
                              </button>
                            </>
                          )}
                          <button
                            className="secondary-btn small-btn"
                            disabled={isViewOnly || checkinEmail === item.email}
                            title={isViewOnly ? 'View-only login' : undefined}
                            onClick={() => handleToggleCheckin(item.email, !item.checked_in)}
                          >
                            {checkinEmail === item.email
                              ? '…'
                              : item.checked_in
                              ? 'Undo check-in'
                              : 'Check in'}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="row-detail">
                          <td colSpan={8}>
                            <div className="detail-grid">
                              <div className="detail-item">
                                <span>Phone</span>
                                <strong>{item.phone ? `${item.country_code || '+1'} ${item.phone}` : '—'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>Batch</span>
                                <strong>{item.batch || '—'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>College</span>
                                <strong>{item.college || '—'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>LinkedIn / contact</span>
                                <strong>{item.linkedin || '—'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>Confirmed via</span>
                                <strong>{item.payment_method || '—'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>Intends to pay via</span>
                                <strong>{item.selected_payment_method || '—'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>Volunteer?</span>
                                <strong>{item.volunteer ? 'Yes' : 'No'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>Looking forward to</span>
                                <strong>{(item.expectations || []).join(', ') || '—'}</strong>
                              </div>
                              <div className="detail-item">
                                <span>Submitted</span>
                                <strong>{new Date(item.created_at).toLocaleString()}</strong>
                              </div>
                              {item.previously_refunded_at && (
                                <div className="detail-item detail-item-warn">
                                  <span>Previously refunded</span>
                                  <strong>
                                    {new Date(item.previously_refunded_at).toLocaleString()}
                                    {item.previously_refunded_ticket_code ? ` (ref ${item.previously_refunded_ticket_code})` : ''}
                                    {item.refund_count > 1 ? ` — ${item.refund_count}× total` : ''}
                                  </strong>
                                </div>
                              )}
                              {item.previously_declined_at && (
                                <div className="detail-item detail-item-warn">
                                  <span>Previously declined</span>
                                  <strong>{new Date(item.previously_declined_at).toLocaleString()}</strong>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
            {data.items.length === 0 && <p className="empty-state">No registrations yet.</p>}
            {data.items.length > 0 && filteredItems.length === 0 && (
              <p className="empty-state">No registrations match the current search/filter.</p>
            )}
          </div>
        </>
      )}
    </main>
  )
}
