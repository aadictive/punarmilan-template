import { useEffect, useState } from 'react'
import './RegisterPage.css'
import eventPhoto from './assets/event-photo.jpg'
import venmoQr from './assets/venmo-qr.png'
import zelleQr from './assets/zelle-qr.png'
import chapter, { phoneHref } from './chapter.js'
import RichText from './richText.jsx'

const METHOD_LABELS = { venmo: 'Venmo', zelle: 'Zelle', card: 'Credit card' }

const { event: EVENT, contact: CONTACT } = chapter

const siteFooter = (
  <footer className="site-footer">
    Have any questions about the event or payment, or suggestions? Reach out to {CONTACT.name} at{' '}
    <a href={`mailto:${CONTACT.email}`}>{CONTACT.email}</a>
    {CONTACT.phone && (
      <>
        {' '}/ <a href={phoneHref(CONTACT.phone)}>{CONTACT.phone}</a>
      </>
    )}
    .
  </footer>
)

const REGISTER_ENDPOINT = import.meta.env.VITE_REGISTER_ENDPOINT || 'https://REPLACE-WITH-YOUR-LAMBDA-URL'
const TRACK_VIEW_ENDPOINT = import.meta.env.VITE_TRACK_VIEW_ENDPOINT || 'https://REPLACE-WITH-YOUR-LAMBDA-URL'
const CONFIG_ENDPOINT = import.meta.env.VITE_CONFIG_ENDPOINT || 'https://REPLACE-WITH-YOUR-LAMBDA-URL'
const CHECKOUT_ENDPOINT = import.meta.env.VITE_CHECKOUT_ENDPOINT || 'https://REPLACE-WITH-YOUR-LAMBDA-URL'
const SELECT_METHOD_ENDPOINT = import.meta.env.VITE_SELECT_METHOD_ENDPOINT || 'https://REPLACE-WITH-YOUR-LAMBDA-URL'
const SEND_INSTRUCTIONS_ENDPOINT = import.meta.env.VITE_SEND_INSTRUCTIONS_ENDPOINT || 'https://REPLACE-WITH-YOUR-LAMBDA-URL'

const EXPECTATION_OPTIONS = chapter.registration_form.expectation_options

const EMPTY_FORM = {
  name: '',
  email: '',
  countryCode: '+1',
  phone: '',
  batch: '',
  college: '',
  linkedin: '',
  volunteer: false,
  expectations: [],
}

function formatDollars(cents) {
  return `$${(cents / 100).toFixed(2)}`
}

function venmoProfileUrl(handle) {
  const username = handle.replace(/^@/, '').trim()
  return `https://venmo.com/u/${encodeURIComponent(username)}`
}

function initialStep() {
  const params = new URLSearchParams(window.location.search)
  if (params.get('paid') === '1') return 'paid-redirect'
  return 'form'
}

// Invite emails link back here with ?name=&email= pre-filled so recipients
// don't have to retype what we already know about them.
function initialForm() {
  const params = new URLSearchParams(window.location.search)
  const name = params.get('name') || ''
  const email = params.get('email') || ''
  if (!name && !email) return EMPTY_FORM
  return { ...EMPTY_FORM, name, email }
}

export default function RegisterPage() {
  const [form, setForm] = useState(initialForm)
  const [step, setStep] = useState(initialStep) // form | confirm | registered | paid-redirect | awaiting-confirmation
  const [status, setStatus] = useState('idle') // idle | loading | error
  const [errorMsg, setErrorMsg] = useState('')
  const [config, setConfig] = useState(null)
  const [registration, setRegistration] = useState(null)
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [checkoutError, setCheckoutError] = useState('')
  const [selectedMethod, setSelectedMethod] = useState(null) // 'venmo' | 'zelle' | 'card'
  const [priorMethod, setPriorMethod] = useState(null) // payment method already on file for this email, if any
  const [pendingMethodSwitch, setPendingMethodSwitch] = useState(null) // method the attendee just clicked, awaiting confirmation
  const [zelleCopied, setZelleCopied] = useState(false)
  const [instructionsSent, setInstructionsSent] = useState(false)
  const [sendingInstructions, setSendingInstructions] = useState(false)
  const [sendInstructionsError, setSendInstructionsError] = useState('')
  const [paymentClaimed, setPaymentClaimed] = useState(false)

  useEffect(() => {
    fetch(CONFIG_ENDPOINT)
      .then((res) => res.json())
      .then(setConfig)
      .catch(() => setConfig({ ticket_price_cents: 6500, stripe_enabled: false, manual_payment_enabled: false }))
  }, [])

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  function toggleExpectation(option) {
    setForm((f) => ({
      ...f,
      expectations: f.expectations.includes(option)
        ? f.expectations.filter((e) => e !== option)
        : [...f.expectations, option],
    }))
  }

  function handleContinueToConfirm(e) {
    e.preventDefault()
    setErrorMsg('')
    // Fire-and-forget: records that this person reached the price screen, even
    // if they back out from here - lets the organizer see drop-off after the
    // price is shown, not just completed registrations.
    fetch(TRACK_VIEW_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    }).catch(() => {})
    setStep('confirm')
  }

  async function handleConfirmRegister() {
    setStatus('loading')
    setErrorMsg('')
    try {
      const res = await fetch(REGISTER_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Something went wrong.')
      setRegistration(data)
      // If this email already had a payment method on file (e.g. they're
      // resubmitting from a different session), reflect that instead of
      // showing an empty, unselected radio group.
      const prior = data.prior_selected_payment_method || null
      setPriorMethod(prior)
      setSelectedMethod(prior)
      setStatus('idle')
      setStep('registered')
    } catch (err) {
      setStatus('error')
      setErrorMsg(err.message)
    }
  }

  function handleCopyZelle(handle) {
    navigator.clipboard?.writeText(handle).then(() => {
      setZelleCopied(true)
      setTimeout(() => setZelleCopied(false), 2000)
    }).catch(() => {})
  }

  function handleSelectMethod(methodValue) {
    // Already paying via a different method? Ask before silently switching -
    // a Venmo/Zelle payment can take a while for an admin to reconcile, so
    // jumping straight to "pay by card" here could mean paying twice.
    if (priorMethod && priorMethod !== methodValue) {
      setPendingMethodSwitch(methodValue)
      return
    }
    applyMethodSelection(methodValue)
  }

  function applyMethodSelection(methodValue) {
    setSelectedMethod(methodValue)
    setPriorMethod(methodValue)
    setInstructionsSent(false)
    setSendInstructionsError('')
    setPaymentClaimed(false)
    fetch(SELECT_METHOD_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: form.email, method: methodValue }),
    }).catch(() => {}) // best-effort - doesn't block the UI either way
  }

  function confirmMethodSwitch() {
    applyMethodSelection(pendingMethodSwitch)
    setPendingMethodSwitch(null)
  }

  function cancelMethodSwitch() {
    setPendingMethodSwitch(null)
  }

  async function handleSendInstructions(methodValue) {
    setSendingInstructions(true)
    setSendInstructionsError('')
    try {
      const res = await fetch(SEND_INSTRUCTIONS_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: form.email, method: methodValue }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Something went wrong.')
      setInstructionsSent(true)
      setStep('awaiting-confirmation')
    } catch (err) {
      setSendInstructionsError(err.message)
    } finally {
      setSendingInstructions(false)
    }
  }

  function handleClaimPayment() {
    // Just an attendee's own claim, not a real confirmation - an admin still
    // has to see the actual Venmo/Zelle transaction before marking this
    // registration paid. No email, no API call, just acknowledges the click.
    setPaymentClaimed(true)
    setStep('awaiting-confirmation')
  }

  async function handlePayByCard() {
    setCheckoutLoading(true)
    setCheckoutError('')
    try {
      const res = await fetch(CHECKOUT_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: form.email }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Something went wrong.')
      window.location.href = data.url
    } catch (err) {
      setCheckoutError(err.message)
      setCheckoutLoading(false)
    }
  }

  function resetAll() {
    setForm(EMPTY_FORM)
    setStep('form')
    setRegistration(null)
    setStatus('idle')
    setErrorMsg('')
    setCheckoutError('')
    setSelectedMethod(null)
    setPriorMethod(null)
    setPendingMethodSwitch(null)
    setInstructionsSent(false)
    setSendInstructionsError('')
    setPaymentClaimed(false)
  }

  const unitPriceCents = config?.ticket_price_cents ?? 6500

  const leftPanel = (
    <section className="split-left" style={{ backgroundImage: `url(${eventPhoto})` }}>
      <div className="split-left-overlay" />
      <div className="split-left-content">
        <div className="event-header">
          <div className="calendar-badge" aria-hidden="true">
            <span className="calendar-badge-month">{EVENT.date_badge.month}</span>
            <span className="calendar-badge-day">{EVENT.date_badge.day}</span>
            <span className="calendar-badge-year">{EVENT.date_badge.year}</span>
          </div>
          <div>
            <p className="kicker">{EVENT.city_label}</p>
            <h1 className="display-hero">{EVENT.name}</h1>
          </div>
        </div>
        <div className="hero-rule" aria-hidden="true" />
        <div className="hero-facts">
          <strong>{EVENT.date_label}</strong>
          <span className="dot" aria-hidden="true">•</span>
          <strong>{EVENT.time_label}</strong>
        </div>
        <p className="venue-line">
          📍{' '}
          {EVENT.venue_maps_url ? (
            <a href={EVENT.venue_maps_url} target="_blank" rel="noreferrer">
              <strong>{EVENT.venue_name}</strong>, {EVENT.venue_address}
            </a>
          ) : (
            <span>
              <strong>{EVENT.venue_name}</strong>, {EVENT.venue_address}
            </span>
          )}
        </p>
        <RichText className="body-lg hero-blurb" text={chapter.content.hero_blurb} />
      </div>
    </section>
  )

  if (step === 'paid-redirect') {
    return (
      <>
        <main className="split">
          {leftPanel}
          <section className="split-right">
            <div className="card confirmation">
              <p className="kicker">Payment received</p>
              <h1 className="display-lg">🎉 You're all set!</h1>
              <p className="body-lg">
                Your payment went through and your registration is confirmed. Check your email for
                your e-ticket — it has a QR code for quick check-in at the door.
              </p>
              <button
                type="button"
                className="secondary-btn"
                onClick={() => {
                  window.history.replaceState({}, '', window.location.pathname)
                  resetAll()
                }}
              >
                Register another attendee
              </button>
            </div>
          </section>
        </main>
        {siteFooter}
      </>
    )
  }

  if (step === 'awaiting-confirmation') {
    return (
      <>
        <main className="split">
          {leftPanel}
          <section className="split-right">
            <div className="card confirmation">
              <p className="kicker">Registration received</p>
              <h1 className="display-lg">Almost there, {form.name.split(' ')[0]}.</h1>
              <p className="body-lg">
                {paymentClaimed ? (
                  <>Thanks for letting us know! We'll confirm your payment and email you once your
                  registration is finalized.</>
                ) : (
                  <>Check <strong>{form.email}</strong> for the payment instructions we just sent. Once
                  we confirm your payment, you'll get another email finalizing your registration.</>
                )}
              </p>
              <button type="button" className="secondary-btn" onClick={resetAll}>
                Register another attendee
              </button>
            </div>
          </section>
        </main>
        {siteFooter}
      </>
    )
  }

  if (step === 'registered' && registration) {
    return (
      <>
      <main className="split">
        {leftPanel}
        <section className="split-right">
          <div className="card confirmation">
            <p className="kicker">Registration received</p>
            <h1 className="display-lg">You're almost in, {form.name.split(' ')[0]}.</h1>
            <p className="body-lg">
              <strong>{formatDollars(registration.amount_cents)}</strong>. Reference code:{' '}
              <strong>{registration.ticket_code}</strong>.
            </p>

            <fieldset className="field payment-method-select">
              <legend>How would you like to pay?</legend>
              <div className="radio-options">
                {config?.venmo_handle && (
                  <label className={`radio-option${selectedMethod === 'venmo' ? ' radio-option-active' : ''}`}>
                    <input
                      type="radio"
                      name="paymethod"
                      checked={selectedMethod === 'venmo'}
                      onChange={() => handleSelectMethod('venmo')}
                    />
                    Venmo
                  </label>
                )}
                {config?.zelle_handle && (
                  <label className={`radio-option${selectedMethod === 'zelle' ? ' radio-option-active' : ''}`}>
                    <input
                      type="radio"
                      name="paymethod"
                      checked={selectedMethod === 'zelle'}
                      onChange={() => handleSelectMethod('zelle')}
                    />
                    Zelle
                  </label>
                )}
                <label className={`radio-option${selectedMethod === 'card' ? ' radio-option-active' : ''}`}>
                  <input
                    type="radio"
                    name="paymethod"
                    checked={selectedMethod === 'card'}
                    onChange={() => handleSelectMethod('card')}
                  />
                  Credit card{config?.card_price_cents ? ` (${formatDollars(config.card_price_cents)})` : ''}
                </label>
              </div>
            </fieldset>

            {selectedMethod === 'venmo' && config?.venmo_handle && (
              <div className="manual-payment">
                <div className="manual-payment-method">
                  <img className="payment-qr" src={venmoQr} alt="Venmo QR code" />
                  <p>
                    Venmo: <strong>{config.venmo_handle}</strong>
                    <br />
                    <span className="manual-payment-hint">Scan with another device, or use the button below on this one</span>
                  </p>
                </div>
                <a
                  className="secondary-btn payment-link-btn"
                  href={venmoProfileUrl(config.venmo_handle)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open in Venmo →
                </a>
                <p className="manual-payment-note">
                  Send <strong>{formatDollars(registration.amount_cents)}</strong> and include your full
                  name or email (<strong>{form.name || form.email}</strong>, as entered on this
                  registration) in the payment memo so we can match it to your registration.
                </p>
                <button
                  type="button"
                  className="submit-btn"
                  onClick={() => handleSendInstructions('venmo')}
                  disabled={sendingInstructions}
                >
                  {sendingInstructions ? 'Sending…' : 'Email me these instructions & finish registering'}
                </button>
                <button type="button" className="submit-btn" onClick={handleClaimPayment}>
                  I've already made the payment
                </button>
                {sendInstructionsError && <p className="error-text">{sendInstructionsError}</p>}
              </div>
            )}

            {selectedMethod === 'zelle' && config?.zelle_handle && (
              <div className="manual-payment">
                <div className="manual-payment-method">
                  <img className="payment-qr" src={zelleQr} alt="Zelle QR code" />
                  <p>
                    Zelle: <strong>{config.zelle_handle}</strong>
                    <br />
                    <span className="manual-payment-hint">
                      Zelle has no universal pay-link like Venmo, so this QR just gets the contact into
                      your phone — send from your banking app's Zelle screen.
                    </span>
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-btn payment-link-btn"
                  onClick={() => handleCopyZelle(config.zelle_handle)}
                >
                  {zelleCopied ? 'Copied!' : 'Copy Zelle contact'}
                </button>
                <p className="manual-payment-note">
                  Send <strong>{formatDollars(registration.amount_cents)}</strong> and include your full
                  name or email (<strong>{form.name || form.email}</strong>, as entered on this
                  registration) in the payment memo so we can match it to your registration.
                </p>
                <button
                  type="button"
                  className="submit-btn"
                  onClick={() => handleSendInstructions('zelle')}
                  disabled={sendingInstructions}
                >
                  {sendingInstructions ? 'Sending…' : 'Email me these instructions & finish registering'}
                </button>
                <button type="button" className="submit-btn" onClick={handleClaimPayment}>
                  I've already made the payment
                </button>
                {sendInstructionsError && <p className="error-text">{sendInstructionsError}</p>}
              </div>
            )}

            {selectedMethod === 'card' && (
              config?.stripe_enabled ? (
                <div className="manual-payment">
                  <p className="manual-payment-note">
                    Includes a card processing fee ({formatDollars(unitPriceCents)} ticket +{' '}
                    {formatDollars((config?.card_price_cents ?? unitPriceCents) - unitPriceCents)} fee) — Venmo
                    and Zelle have no added fee.
                  </p>
                  <button className="submit-btn" onClick={handlePayByCard} disabled={checkoutLoading}>
                    {checkoutLoading
                      ? 'Redirecting…'
                      : `Pay ${config?.card_price_cents ? formatDollars(config.card_price_cents) : ''} by card`}
                  </button>
                  {checkoutError && <p className="error-text">{checkoutError}</p>}
                </div>
              ) : (
                <div className="manual-payment">
                  <p className="manual-payment-note">
                    Card payments aren't set up yet — check back soon, or pick Venmo/Zelle above.
                  </p>
                </div>
              )
            )}

            <button type="button" className="secondary-btn" onClick={resetAll}>
              Register another attendee
            </button>
          </div>
        </section>

        {pendingMethodSwitch && (
          <div className="modal-overlay" role="dialog" aria-modal="true">
            <div className="modal-card">
              <h2 className="modal-title">Switch payment method?</h2>
              <p className="modal-body">
                You previously chose to pay via <strong>{METHOD_LABELS[priorMethod]}</strong>. If
                you already sent that payment, please don't pay again — we'll confirm it once
                received. Otherwise, you can switch to <strong>{METHOD_LABELS[pendingMethodSwitch]}</strong>{' '}
                instead.
              </p>
              <div className="modal-actions">
                <button type="button" className="submit-btn" onClick={confirmMethodSwitch}>
                  Switch to {METHOD_LABELS[pendingMethodSwitch]}
                </button>
                <button type="button" className="modal-link-btn" onClick={cancelMethodSwitch}>
                  Continue with {METHOD_LABELS[priorMethod]}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
      {siteFooter}
      </>
    )
  }

  if (step === 'confirm') {
    return (
      <>
      <main className="split">
        {leftPanel}
        <section className="split-right">
          <div className="card confirmation">
            <p className="kicker">One more step</p>
            <h1 className="display-lg">Confirm your email</h1>
            <p className="body-lg">
              Your e-ticket will be sent to <strong>{form.email}</strong>.
            </p>

            <div className="price-summary">
              <span>Price per attendee</span>
              <strong>{formatDollars(unitPriceCents)}</strong>
            </div>

            {status === 'error' && <p className="error-text">{errorMsg}</p>}

            <button type="button" className="submit-btn" onClick={handleConfirmRegister} disabled={status === 'loading'}>
              {status === 'loading' ? 'Registering…' : 'Confirm & register'}
            </button>
            <button type="button" className="secondary-btn" onClick={() => setStep('form')} disabled={status === 'loading'}>
              ← Edit details
            </button>
          </div>
        </section>
      </main>
      {siteFooter}
      </>
    )
  }

  return (
    <>
    <main className="split">
      {leftPanel}

      <section className="split-right">
        <div className="card form-card">
          <h2 className="display-sm">Register your spot</h2>
          <p className="form-note">Submit one form per attendee.</p>

          <form onSubmit={handleContinueToConfirm} className="form">
            <div className="field-row">
              <label className="field">
                <span>Full name</span>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => update('name', e.target.value)}
                  placeholder="e.g. John Doe"
                />
              </label>

              <label className="field">
                <span>Email</span>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => update('email', e.target.value)}
                  placeholder="you@example.com"
                />
              </label>
            </div>

            <div className="field-row">
              <label className="field">
                <span>Batch / graduation year</span>
                <input
                  type="text"
                  required
                  value={form.batch}
                  onChange={(e) => update('batch', e.target.value)}
                  placeholder="e.g. 2015"
                />
              </label>

              <label className="field">
                <span>College / institution</span>
                <input
                  type="text"
                  required
                  value={form.college}
                  onChange={(e) => update('college', e.target.value)}
                  placeholder={chapter.registration_form.college_placeholder}
                />
              </label>
            </div>

            <div className="field-row">
              <label className="field">
                <span>Phone</span>
                <div className="phone-input-group">
                  <select
                    className="phone-country-select"
                    aria-label="Country code"
                    value={form.countryCode}
                    onChange={(e) => update('countryCode', e.target.value)}
                  >
                    <option value="+1">🇺🇸 +1</option>
                    <option value="+91">🇮🇳 +91</option>
                  </select>
                  <input
                    type="tel"
                    inputMode="numeric"
                    required
                    pattern="\d{10}"
                    maxLength={10}
                    title="10-digit phone number, no letters or symbols"
                    value={form.phone}
                    onChange={(e) => update('phone', e.target.value.replace(/\D/g, '').slice(0, 10))}
                    placeholder="e.g. 5551234567"
                  />
                </div>
              </label>

              <label className="field">
                <span>LinkedIn / contact (optional)</span>
                <input
                  type="text"
                  value={form.linkedin}
                  onChange={(e) => update('linkedin', e.target.value)}
                  placeholder="linkedin.com/in/you"
                />
              </label>
            </div>

            <fieldset className="field chip-field">
              <legend>What are you most looking forward to? (optional)</legend>
              <div className="chip-options">
                {EXPECTATION_OPTIONS.map((option) => (
                  <label
                    key={option}
                    className={`chip${form.expectations.includes(option) ? ' chip-active' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={form.expectations.includes(option)}
                      onChange={() => toggleExpectation(option)}
                    />
                    {option}
                  </label>
                ))}
              </div>
            </fieldset>

            <label className="field checkbox-field">
              <input
                type="checkbox"
                checked={form.volunteer}
                onChange={(e) => update('volunteer', e.target.checked)}
              />
              <span>
                🙋 Want to be part of the crew that keeps the day running smoothly? We could use a
                few hands for check-in, seating &amp; crowd flow — count me in!
              </span>
            </label>

            <button type="submit" className="submit-btn">
              Continue
            </button>
          </form>
        </div>
      </section>
    </main>
    {siteFooter}
    </>
  )
}
