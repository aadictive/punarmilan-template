import { useEffect, useRef, useState } from 'react'
import { Html5Qrcode } from 'html5-qrcode'
import './CheckinPage.css'

const CHECKIN_ENDPOINT = import.meta.env.VITE_CHECKIN_ENDPOINT || 'https://REPLACE-WITH-YOUR-LAMBDA-URL'
const SCANNER_ELEMENT_ID = 'checkin-qr-reader'
const KEY_STORAGE = 'punarmilan-checkin-key'

function getKey() {
  const fromUrl = new URLSearchParams(window.location.search).get('key')
  if (fromUrl) {
    localStorage.setItem(KEY_STORAGE, fromUrl)
    return fromUrl
  }
  try {
    return localStorage.getItem(KEY_STORAGE) || ''
  } catch {
    return ''
  }
}

export default function CheckinPage() {
  const [checkinKey] = useState(getKey)
  const [scanning, setScanning] = useState(false)
  const [manualCode, setManualCode] = useState('')
  const [result, setResult] = useState(null) // { kind: 'success'|'warning'|'error', ... } - last scan, stays visible after the modal closes
  const [modalOpen, setModalOpen] = useState(false)
  const [checkedInCount, setCheckedInCount] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const scannerRef = useRef(null)
  const lastScannedRef = useRef({ code: '', at: 0 })

  function showResult(r) {
    setResult(r)
    setModalOpen(true)
  }

  useEffect(() => {
    return () => {
      if (scannerRef.current) {
        scannerRef.current.stop().catch(() => {})
      }
    }
  }, [])

  async function startScanning() {
    setResult(null)
    setScanning(true)
    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID)
    scannerRef.current = scanner
    try {
      await scanner.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: 240 },
        (decodedText) => {
          // Debounce: the camera keeps firing on the same code every frame
          // while it's in view - only act on it once per ~3s.
          const now = Date.now()
          if (decodedText === lastScannedRef.current.code && now - lastScannedRef.current.at < 3000) return
          lastScannedRef.current = { code: decodedText, at: now }
          // Freeze the video feed the moment something is decoded, so the
          // camera isn't still scanning (and potentially firing again)
          // underneath the verification modal - resumes on "Scan more".
          scanner.pause(true)
          submitCode(decodedText)
        },
        () => {} // per-frame "no QR found" - expected constantly, ignore
      )
    } catch (err) {
      setScanning(false)
      showResult({ kind: 'error', message: `Couldn't start the camera: ${err.message || err}` })
    }
  }

  async function stopScanning() {
    if (scannerRef.current) {
      try {
        await scannerRef.current.stop()
      } catch {
        // ignore - already stopped
      }
      scannerRef.current = null
    }
    setScanning(false)
  }

  async function submitCode(code) {
    if (!code.trim() || submitting) return
    setSubmitting(true)
    setResult(null)
    try {
      const res = await fetch(CHECKIN_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim(), key: checkinKey }),
      })
      const data = await res.json()
      if (res.status === 401) {
        showResult({ kind: 'error', message: 'This check-in link is invalid or expired. Get a fresh link from the organizer.' })
      } else if (!res.ok) {
        showResult({ kind: 'error', message: data.error || 'Something went wrong.' })
      } else {
        setCheckedInCount(data.checked_in_count)
        if (data.already_checked_in) {
          showResult({
            kind: 'warning',
            message: `Already checked in at ${new Date(data.checked_in_at).toLocaleTimeString()}`,
            name: data.name,
            batch: data.batch,
            college: data.college,
          })
        } else if (data.status !== 'paid') {
          showResult({
            kind: 'warning',
            message: `Found, but payment status is "${data.status}" — confirm payment before letting them in.`,
            name: data.name,
            batch: data.batch,
            college: data.college,
          })
        } else {
          showResult({ kind: 'success', message: 'Checked in!', name: data.name, batch: data.batch, college: data.college })
        }
      }
    } catch (err) {
      showResult({ kind: 'error', message: 'Network error - please try again.' })
    } finally {
      setSubmitting(false)
      setManualCode('')
    }
  }

  function handleManualSubmit(e) {
    e.preventDefault()
    submitCode(manualCode)
  }

  // "OK" - done for now, close the modal and stop the camera outright.
  function handleModalOk() {
    setModalOpen(false)
    stopScanning()
  }

  // "Scan more" - close the modal and get straight back to scanning: resume
  // the paused camera if it's still running, or start it fresh if this scan
  // came from manual entry (or the camera failed to start in the first place).
  function handleModalScanMore() {
    setModalOpen(false)
    if (scannerRef.current) {
      scannerRef.current.resume()
    } else {
      startScanning()
    }
  }

  if (!checkinKey) {
    return (
      <main className="checkin-page">
        <div className="checkin-card">
          <h1>Check-in</h1>
          <p>This link is missing its access key. Ask the organizer for the correct check-in link.</p>
        </div>
      </main>
    )
  }

  return (
    <main className="checkin-page">
      <div className="checkin-card">
        <h1>Door Check-in</h1>
        {checkedInCount !== null && <p className="checkin-count">{checkedInCount} checked in so far</p>}

        <div id={SCANNER_ELEMENT_ID} className={scanning ? 'checkin-scanner active' : 'checkin-scanner'} />

        {!scanning ? (
          <button type="button" className="checkin-btn checkin-btn-primary" onClick={startScanning}>
            📷 Start scanning
          </button>
        ) : (
          <button type="button" className="checkin-btn checkin-btn-secondary" onClick={stopScanning}>
            Stop camera
          </button>
        )}

        <form onSubmit={handleManualSubmit} className="checkin-manual">
          <input
            type="text"
            placeholder="Or type the reference code"
            value={manualCode}
            onChange={(e) => setManualCode(e.target.value)}
          />
          <button type="submit" className="checkin-btn checkin-btn-secondary" disabled={submitting || !manualCode.trim()}>
            {submitting ? '…' : 'Check in'}
          </button>
        </form>

        {result && (
          <div className={`checkin-result checkin-result-${result.kind}`}>
            <p className="checkin-result-label">Last scanned</p>
            {result.kind === 'success' && <p className="checkin-result-icon">✅</p>}
            {result.kind === 'warning' && <p className="checkin-result-icon">⚠️</p>}
            {result.kind === 'error' && <p className="checkin-result-icon">❌</p>}
            {result.name && (
              <p className="checkin-result-name">
                {result.name}
                {(result.batch || result.college) && (
                  <span className="checkin-result-sub">
                    {' '}
                    ({[result.batch, result.college].filter(Boolean).join(', ')})
                  </span>
                )}
              </p>
            )}
            <p className="checkin-result-message">{result.message}</p>
          </div>
        )}
      </div>

      {modalOpen && result && (
        <div className="checkin-modal-overlay" role="dialog" aria-modal="true">
          <div className={`checkin-modal checkin-modal-${result.kind}`}>
            {result.kind === 'success' && <p className="checkin-modal-icon">✅</p>}
            {result.kind === 'warning' && <p className="checkin-modal-icon">⚠️</p>}
            {result.kind === 'error' && <p className="checkin-modal-icon">❌</p>}
            {result.name && (
              <p className="checkin-modal-name">
                {result.name}
                {(result.batch || result.college) && (
                  <span className="checkin-modal-sub">
                    {' '}
                    ({[result.batch, result.college].filter(Boolean).join(', ')})
                  </span>
                )}
              </p>
            )}
            <p className="checkin-modal-message">{result.message}</p>
            <div className="checkin-modal-actions">
              <button type="button" className="checkin-btn checkin-btn-secondary" onClick={handleModalOk}>
                OK
              </button>
              <button type="button" className="checkin-btn checkin-btn-primary" onClick={handleModalScanMore}>
                Scan more
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
