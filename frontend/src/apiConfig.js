// Dynamic API base URL configuration
// Supports Vercel cloud deployment, Render backend, local dev, and Electron desktop app

const getApiUrl = () => {
  // 1. Explicit Vite env variable (e.g. set in Vercel: VITE_API_BASE_URL=https://phantom-tg-backend.onrender.com)
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')
  }

  // 2. Local desktop / dev environment
  if (typeof window !== 'undefined') {
    const { hostname } = window.location
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '') {
      return 'http://127.0.0.1:8000'
    }
    // 3. If hosted on a web domain without explicit VITE_API_BASE_URL, default to same-origin or localStorage override
    const saved = localStorage.getItem('phantom_api_url')
    if (saved) return saved.replace(/\/+$/, '')
  }

  return 'http://127.0.0.1:8000'
}

export const API = getApiUrl()

export const setApiUrl = (url) => {
  if (typeof window !== 'undefined') {
    localStorage.setItem('phantom_api_url', url)
    window.location.reload()
  }
}
