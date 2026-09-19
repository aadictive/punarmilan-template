import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import RegisterPage from './RegisterPage.jsx'
import TicketsAdminPage from './TicketsAdminPage.jsx'
import DeclinePage from './DeclinePage.jsx'

// Lazy-loaded: pulls in the QR-scanning library, which regular registrants
// visiting "/" never need to download.
const CheckinPage = lazy(() => import('./CheckinPage.jsx'))

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RegisterPage />} />
        <Route path="/admin" element={<TicketsAdminPage />} />
        <Route path="/decline" element={<DeclinePage />} />
        <Route
          path="/checkin"
          element={
            <Suspense fallback={null}>
              <CheckinPage />
            </Suspense>
          }
        />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
