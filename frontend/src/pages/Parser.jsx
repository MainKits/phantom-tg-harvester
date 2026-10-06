import { useState, useEffect, useRef } from 'react'
import { Search, Play, Square, Download, Trash2, Filter, Upload, RefreshCw } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function Parser() {
  const [chatLinks, setChatLinks] = useState('')
  const [onlineFilter, setOnlineFilter] = useState('24')
  const [activeOnly, setActiveOnly] = useState(false)
  const [skipAdmins, setSkipAdmins] = useState(true)
  const [skipBots, setSkipBots] = useState(true)
  const [parsing, setParsing] = useState(false)
  const [progress, setProgress] = useState(null)
  const [users, setUsers] = useState([])
  const [totalParsed, setTotalParsed] = useState(0)
  const pollRef = useRef(null)

  const fetchUsers = async () => {
    try {
      const res = await fetch(`${API}/api/parser/users?limit=50`)
      if (res.ok) {
        const data = await res.json()
        setUsers(data.users || [])
        setTotalParsed(data.total || 0)
      }
    } catch {}
  }

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API}/api/parser/status`)
      if (res.ok) {
        const data = await res.json()
        setProgress(data)
        if (data.status === 'running') {
          setParsing(true)
          fetchUsers()
        } else if (data.status === 'done' || data.status === 'stopped' || data.status === 'error') {
          setParsing(false)
          fetchUsers()
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
        }
      }
    } catch {}
  }

  useEffect(() => {
    fetchUsers()
    fetchStatus()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const startPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(() => { fetchStatus() }, 2000)
  }

  const handleStart = async () => {
    if (!chatLinks.trim()) return alert('Вставте посилання на чати або завантажте файл')
    setParsing(true)
    setProgress({ status: 'running', parsed: 0, total: 0, current_chat: '' })
    try {
      const form = new FormData()
      form.append('chat_links', chatLinks)
      form.append('online_filter', onlineFilter || '')
      form.append('active_writers_only', activeOnly ? 'true' : 'false')
      form.append('skip_admins', skipAdmins ? 'true' : 'false')
      form.append('skip_bots', skipBots ? 'true' : 'false')
      const res = await fetch(`${API}/api/parser/start`, { method: 'POST', body: form })
      if (res.ok) {
        startPolling()
      } else {
        const err = await res.json()
        alert(err.detail || 'Помилка')
        setParsing(false)
      }
    } catch {
      alert('Бекенд не запущено')
      setParsing(false)
    }
  }

  const handleStop = async () => {
    setParsing(false)
    try { await fetch(`${API}/api/parser/stop`, { method: 'POST' }) } catch {}
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    fetchUsers()
  }

  const handleClear = async () => {
    if (!confirm('Очистити всю базу спарсених юзерів?')) return
    try {
      await fetch(`${API}/api/parser/users`, { method: 'DELETE' })
      setUsers([])
      setTotalParsed(0)
    } catch { alert('Бекенд не запущено') }
  }

  const handleExport = (format) => {
    window.open(`${API}/api/parser/export/${format}`, '_blank')
  }

  const handleFileUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API}/api/parser/upload-links`, { method: 'POST', body: form })
      if (res.ok) {
        const data = await res.json()
        setChatLinks(data.links.join('\n'))
        alert(`✅ Завантажено ${data.count} посилань з файлу`)
      }
    } catch { alert('Бекенд не запущено') }
    e.target.value = ''
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Parser</h2>
          <p className="subtitle">Збір аудиторії з Telegram-чатів</p>
        </div>
        <div className="btn-group">
          <button className="btn btn-secondary btn-sm" onClick={fetchUsers}>
            <RefreshCw size={14} /> Оновити
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => handleExport('txt')} disabled={totalParsed === 0}>
            <Download size={14} /> .txt
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => handleExport('csv')} disabled={totalParsed === 0}>
            <Download size={14} /> .csv
          </button>
        </div>
      </div>
      <div className="page-body">
        {/* Source links */}
        <div className="card section">
          <div className="card-header">
            <span className="card-title"><Search size={15} /> Джерела для парсингу</span>
            <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
              <Upload size={13} /> Завантажити .txt
              <input type="file" accept=".txt,.csv" style={{ display: 'none' }} onChange={handleFileUpload} />
            </label>
          </div>
          <div className="input-group">
            <label className="input-label">Посилання на чати (по одному на рядок або через кому)</label>
            <textarea
              className="textarea"
              rows={4}
              placeholder={"https://t.me/crypto_ua\nhttps://t.me/ubt_chat\nhttps://t.me/traffic_chat\n\nАбо завантажте файл з Chat Finder →"}
              value={chatLinks}
              onChange={e => setChatLinks(e.target.value)}
            />
          </div>
          {chatLinks.trim() && (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
              📋 {chatLinks.split('\n').filter(l => l.trim()).length} посилань готово
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="card section">
          <div className="card-header">
            <span className="card-title"><Filter size={15} /> Фільтри</span>
          </div>
          <div className="form-grid">
            <div className="input-group">
              <label className="input-label">Онлайн за останні</label>
              <select className="select" value={onlineFilter} onChange={e => setOnlineFilter(e.target.value)}>
                <option value="">Без фільтру</option>
                <option value="24">24 години</option>
                <option value="48">48 годин</option>
                <option value="168">7 днів</option>
              </select>
            </div>
            <div className="input-group" style={{ display: 'flex', flexDirection: 'column', gap: '12px', paddingTop: '20px' }}>
              <div className="toggle-row">
                <div className={`toggle-switch ${activeOnly ? 'on' : ''}`} onClick={() => setActiveOnly(!activeOnly)} />
                <span>Тільки активні (писали повідомлення)</span>
              </div>
              <div className="toggle-row">
                <div className={`toggle-switch ${skipAdmins ? 'on' : ''}`} onClick={() => setSkipAdmins(!skipAdmins)} />
                <span>Пропускати адмінів</span>
              </div>
              <div className="toggle-row">
                <div className={`toggle-switch ${skipBots ? 'on' : ''}`} onClick={() => setSkipBots(!skipBots)} />
                <span>Пропускати ботів</span>
              </div>
            </div>
          </div>
        </div>

        {/* Start / Stop + Progress */}
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
          {!parsing ? (
            <button className="btn btn-primary" onClick={handleStart} disabled={!chatLinks.trim()}>
              <Play size={15} /> Почати парсинг
            </button>
          ) : (
            <button className="btn btn-danger" onClick={handleStop}>
              <Square size={15} /> Зупинити
            </button>
          )}
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {parsing && <span className="badge running"><span className="badge-dot"></span> Парсинг...</span>}
            {' '}Зібрано: <strong style={{ color: 'var(--neon-green)' }}>{totalParsed.toLocaleString()}</strong> користувачів
          </span>
        </div>

        {/* Progress bar */}
        {parsing && progress && (
          <div className="card" style={{ marginTop: '12px', borderColor: 'rgba(0,170,255,0.3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
              <span className="badge running"><span className="badge-dot"></span> Парсинг активний</span>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                Чат: <strong style={{ color: 'var(--text-primary)' }}>@{progress.current_chat || '...'}</strong>
                {' '}| Зібрано: <strong style={{ color: 'var(--neon-green)' }}>{progress.parsed}</strong>
              </span>
            </div>
            {progress.total > 0 && (
              <div style={{ background: 'var(--bg-input)', borderRadius: '4px', height: '6px', overflow: 'hidden' }}>
                <div style={{
                  width: `${Math.min(100, ((progress.parsed || 1) / Math.max(1, progress.total)) * 100)}%`,
                  height: '100%', background: 'var(--accent)', borderRadius: '4px', transition: 'width 0.5s ease',
                }} />
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {progress?.status === 'error' && (
          <div className="card" style={{ marginTop: '12px', borderLeft: '3px solid var(--neon-red)' }}>
            <div style={{ fontSize: '13px', color: 'var(--neon-red)' }}>
              ❌ Помилка: {progress.current_chat || 'Невідома помилка'}
            </div>
          </div>
        )}

        {/* Users table */}
        <div className="card" style={{ marginTop: '20px' }}>
          <div className="card-header">
            <span className="card-title">Зібрані користувачі ({totalParsed})</span>
            {totalParsed > 0 && (
              <button className="btn btn-danger btn-sm" onClick={handleClear}><Trash2 size={13} /> Очистити базу</button>
            )}
          </div>
          {users.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔍</div>
              <div className="empty-state-text">База порожня</div>
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '8px' }}>
                Вставте посилання та запустіть парсинг, або завантажте файл з Chat Finder
              </p>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>User ID</th><th>Username</th><th>Ім'я</th><th>Джерело</th><th>Останній онлайн</th><th>Активний</th></tr>
                </thead>
                <tbody>
                  {users.map((u, i) => (
                    <tr key={i}>
                      <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}>{u.user_id}</td>
                      <td style={{ color: 'var(--accent)' }}>{u.username ? `@${u.username}` : '—'}</td>
                      <td>{u.first_name || '—'} {u.last_name || ''}</td>
                      <td>@{u.source_chat || '—'}</td>
                      <td>{u.last_online || '—'}</td>
                      <td>{u.is_active_writer ? <span className="badge active"><span className="badge-dot"></span> Так</span> : <span className="badge inactive">Ні</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
