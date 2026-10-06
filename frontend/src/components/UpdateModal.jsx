import { useState, useEffect } from 'react'
import { Sparkles, Download, CheckCircle2, AlertCircle, RefreshCw, X, Settings } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function UpdateModal({ isOpen, onClose, updateInfo, onRefresh }) {
  const [downloading, setDownloading] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [error, setError] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [customUrl, setCustomUrl] = useState('')

  useEffect(() => {
    if (updateInfo?.update_url) {
      setCustomUrl(updateInfo.update_url)
    }
  }, [updateInfo])

  if (!isOpen) return null

  const handleInstall = async () => {
    if (!updateInfo?.download_url) {
      alert('Посилання для завантаження відсутнє')
      return
    }
    setDownloading(true)
    setError(null)
    setStatusMsg('⏳ Завантаження нового інсталятора...')

    try {
      const fd = new FormData()
      fd.append('download_url', updateInfo.download_url)
      const res = await fetch(`${API}/api/system/install-update`, {
        method: 'POST',
        body: fd,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Помилка оновлення')
      setStatusMsg('✅ Завантажено! Запускаємо оновлення та перезапуск...')
    } catch (err) {
      setError(err.message)
      setDownloading(false)
    }
  }

  const handleSaveUrl = async () => {
    if (!customUrl.trim()) return
    try {
      const fd = new FormData()
      fd.append('url', customUrl.trim())
      const res = await fetch(`${API}/api/system/set-update-url`, { method: 'POST', body: fd })
      if (res.ok) {
        alert('✅ Посилання оновлень збережено!')
        setShowSettings(false)
        if (onRefresh) onRefresh()
      }
    } catch {}
  }

  return (
    <div className="modal-overlay" onClick={onClose} style={{ zIndex: 10000 }}>
      <div className="modal fade-in" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 className="modal-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={18} color="var(--accent)" /> Оновлення системи
          </h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="btn btn-secondary btn-sm"
              style={{ padding: '4px 8px' }}
              title="Налаштувати URL"
            >
              <Settings size={14} />
            </button>
            <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}>
              <X size={18} />
            </button>
          </div>
        </div>

        {showSettings && (
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: 12, borderRadius: 8, marginBottom: 16 }}>
            <label style={{ fontSize: 12, color: '#aaa', display: 'block', marginBottom: 6 }}>
              URL перевірки оновлень (version.json):
            </label>
            <input
              type="text"
              className="input"
              value={customUrl}
              onChange={e => setCustomUrl(e.target.value)}
              placeholder="https://.../version.json"
              style={{ fontSize: 12, padding: '8px 10px', marginBottom: 8 }}
            />
            <button className="btn btn-primary btn-sm" onClick={handleSaveUrl}>
              Зберегти URL
            </button>
          </div>
        )}

        <div style={{ textAlign: 'center', margin: '20px 0' }}>
          <div style={{ fontSize: 44, marginBottom: 8 }}>
            {updateInfo?.has_update ? '🚀' : '✨'}
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#fff' }}>
            {updateInfo?.has_update
              ? `Доступна нова версія: v${updateInfo.latest_version}!`
              : 'У вас встановлено найновішу версію'}
          </div>
          <div style={{ fontSize: 13, color: '#888', marginTop: 4 }}>
            Поточна версія: <span style={{ color: 'var(--accent)' }}>v{updateInfo?.current_version || '1.0.0'}</span>
          </div>
        </div>

        {updateInfo?.has_update && (
          <div style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 12,
            padding: 16,
            marginBottom: 20
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#aaa', marginBottom: 6 }}>
              Що нового в цій версії:
            </div>
            <div style={{ fontSize: 13, color: '#ddd', whiteSpace: 'pre-line', lineHeight: '1.5' }}>
              {updateInfo.changelog}
            </div>
          </div>
        )}

        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'rgba(255,71,87,0.1)', border: '1px solid rgba(255,71,87,0.3)',
            borderRadius: 8, padding: '10px 14px', color: '#ff6b7a', fontSize: 13, marginBottom: 16
          }}>
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {statusMsg && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'rgba(46,213,115,0.1)', border: '1px solid rgba(46,213,115,0.3)',
            borderRadius: 8, padding: '10px 14px', color: '#2ed573', fontSize: 13, marginBottom: 16
          }}>
            <CheckCircle2 size={16} /> {statusMsg}
          </div>
        )}

        <div className="modal-actions" style={{ marginTop: 20 }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={downloading}>
            Закрити
          </button>
          {updateInfo?.has_update ? (
            <button
              className="btn btn-primary"
              onClick={handleInstall}
              disabled={downloading}
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <Download size={15} /> {downloading ? 'Завантаження...' : '⚡ Оновити зараз'}
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={() => { if (onRefresh) onRefresh() }}
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <RefreshCw size={15} /> Перевірити знову
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
