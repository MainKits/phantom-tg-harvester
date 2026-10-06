// Dynamic API base URL configuration
// Configured to automatically connect to live Render backend for cloud deployments

export const DEFAULT_CLOUD_API = 'https://phantom-tg-harvester.onrender.com'

const getApiUrl = () => {
  if (typeof window !== 'undefined') {
    // 1. Explicit user override in localStorage
    const saved = localStorage.getItem('phantom_api_url')
    if (saved && saved.trim()) return saved.trim().replace(/\/+$/, '')

    // 2. Local dev or Electron desktop
    const { hostname } = window.location
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '') {
      return 'http://127.0.0.1:8000'
    }
  }

  // 3. Vite environment variable if set in Vercel
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')
  }

  // 4. Default to live Render backend
  return DEFAULT_CLOUD_API
}

export const API = getApiUrl()

export const setApiUrl = (url) => {
  if (typeof window !== 'undefined') {
    if (!url || !url.trim()) {
      localStorage.removeItem('phantom_api_url')
    } else {
      localStorage.setItem('phantom_api_url', url.trim())
    }
    window.location.reload()
  }
}
