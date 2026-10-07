import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import AccountManager from './pages/AccountManager'
import Parser from './pages/Parser'
import ChatFinder from './pages/ChatFinder'
import Sender from './pages/Sender'
import Inviter from './pages/Inviter'
import MediaTools from './pages/MediaTools'
import TikTokManager from './pages/TikTokManager'
import AdminLicense from './pages/AdminLicense'
import LicenseScreen from './pages/LicenseScreen'
import { API } from './apiConfig'
import './index.css'

function App() {
  const savedKey = typeof window !== 'undefined' ? localStorage.getItem('phantom_license_key') : null
  const [licenseChecked, setLicenseChecked] = useState(!!savedKey)
  const [licensed, setLicensed] = useState(!!savedKey)
  const [backendOnline, setBackendOnline] = useState(true)

  const checkLicense = async () => {

    // If key is saved locally, keep user logged in immediately (no flicker / wait)
    if (savedKey) {
      setLicensed(true)
    }

    try {
      const url = savedKey
        ? `${API}/api/license/status?key=${encodeURIComponent(savedKey)}`
        : `${API}/api/license/status`
      const res = await fetch(url)
      const data = await res.json()

      if (data.licensed === true) {
        setLicensed(true)
        setBackendOnline(true)
      } else {
        if (data.reason === 'expired' || data.reason === 'revoked') {
          if (typeof window !== 'undefined') localStorage.removeItem('phantom_license_key')
          setLicensed(false)
        } else if (!savedKey) {
          setLicensed(false)
        }
      }
    } catch {
      // Backend asleep or cold start: do not kick user out if key is saved!
      setBackendOnline(false)
      if (!savedKey) {
        setLicensed(false)
      }
    } finally {
      setLicenseChecked(true)
    }
  }

  useEffect(() => {
    checkLicense()
  }, [])

  if (!licenseChecked) {
    return (
      <div style={{ minHeight: '100vh', background: '#0a0a0f', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontFamily: 'Inter, sans-serif' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>👻</div>
          <p style={{ color: '#666' }}>Перевірка ліцензії...</p>
        </div>
      </div>
    )
  }

  if (!licensed) {
    return <LicenseScreen onActivated={() => { setLicensed(true) }} />
  }

  return (
    <BrowserRouter>
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/accounts" element={<AccountManager />} />
          <Route path="/parser" element={<Parser />} />
          <Route path="/chat-finder" element={<ChatFinder />} />
          <Route path="/sender" element={<Sender />} />
          <Route path="/inviter" element={<Inviter />} />
          <Route path="/media-tools" element={<MediaTools />} />
          <Route path="/tiktok-manager" element={<TikTokManager />} />
          <Route path="/admin/license" element={<AdminLicense />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
