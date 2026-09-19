import { useState } from 'react'
import './DeclinePage.css'
import chapter from './chapter.js'

const { event: EVENT, contact: CONTACT } = chapter
const CONTACT_TEXT = CONTACT.phone ? `${CONTACT.name} at ${CONTACT.phone}` : `${CONTACT.name} at ${CONTACT.email}`

const DECLINE_ENDPOINT = import.meta.env.VITE_DECLINE_ENDPOINT || 'https://REPLACE-WITH-YOUR-DECLINE-LAMBDA-URL'

function getParams() {
  const params = new URLSearchParams(window.location.search)
  return {
    name: params.get('name') || '',
    email: params.get('email') || '',
  }
}

export default function DeclinePage() {
  const [{ name, email }] = useState(getParams)
  const [status, setStatus] = useState('confirm') // confirm | submitting | done | already_registered | error

  async function handleConfirm() {
    setStatus('submitting')
    try {
      const res = await fetch(DECLINE_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Something went wrong.')
      setStatus(data.already_registered ? 'already_registered' : 'done')
    } catch {
      setStatus('error')
    }
  }

  if (!email) {
    return (
      <main className="decline-page">
        <div className="decline-card">
          <h1>{EVENT.name}</h1>
          <p>This link is missing some information. Please use the link from your invite email.</p>
        </div>
      </main>
    )
  }

  return (
    <main className="decline-page">
      <div className="decline-card">
        <h1>{EVENT.name}</h1>

        {status === 'confirm' && (
          <>
            <p>Hi {name || 'there'}, sorry to hear you can't make it this year.</p>
            <p className="decline-note">
              Clicking below just lets us know not to follow up — nothing else happens to your
              information.
            </p>
            <button type="button" className="decline-btn" onClick={handleConfirm}>
              Yes, I can't make it
            </button>
            <a className="decline-secondary" href="/">
              Actually, I'd like to register →
            </a>
          </>
        )}

        {status === 'submitting' && <p>Just a moment…</p>}

        {status === 'done' && (
          <>
            <p className="decline-result-icon">👋</p>
            <p>Thanks for letting us know, {name || 'there'} — we've noted you won't be attending.</p>
            <p className="decline-note">
              Change your mind later? You're welcome to{' '}
              <a href="/">register anytime before the event</a>.
            </p>
          </>
        )}

        {status === 'already_registered' && (
          <>
            <p>Looks like you're already registered for the event!</p>
            <p className="decline-note">
              If that's a mistake, contact {CONTACT_TEXT}.
            </p>
          </>
        )}

        {status === 'error' && (
          <p className="decline-error">
            Something went wrong. Please try again, or contact {CONTACT_TEXT}.
          </p>
        )}
      </div>
    </main>
  )
}
