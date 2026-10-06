import { useState, useEffect } from 'react'
import { Plus, Upload, Trash2, Shield, Key, LogIn, RefreshCw, CheckCircle, XCircle } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

const EMPTY_PROXY = { type: 'socks5', host: '', port: '', username: '', password: '' }

export default function AccountManager() {
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [showProxyModal, setShowProxyModal] = useState(null) // account id
  const [proxyForm, setProxyForm] = useState(EMPTY_PROXY)
  const [showAuthModal, setShowAuthModal] = useState(null)  // account object
  const [showSettingsModal, setShowSettingsModal] = useState(false)
  const [newPhone, setNewPhone] = useState('')
  const [authCode, setAuthCode] = useState('')
  const [phoneHash, setPhoneHash] = useState('')
  const [authStep, setAuthStep] = useState('phone')
  const [authLoading, setAuthLoading] = useState(false)
  const [apiId, setApiId] = useState('')
  const [apiHash, setApiHash] = useState('')
  const [apiConfigured, setApiConfigured] = useState(false)
  const [checkingId, setCheckingId] = useState(null)

  // ── Join chat modal ──
  const [showJoinModal, setShowJoinModal] = useState(null)   // account
  const [joinLink, setJoinLink] = useState('')
  const [joinLoading, setJoinLoading] = useState(false)
  const [joinResult, setJoinResult] = useState(null)

  const fetchAccounts = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/accounts/`)
      if (res.ok) {
        const data = await res.json()
        setAccounts(data.accounts || [])
      }
    } catch {}
    setLoading(false)
  }

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API}/api/dashboard/settings`)
      if (res.ok) {
        const data = await res.json()
        setApiConfigured(!!(data.settings?.api_id && data.settings?.api_hash))
        if (data.settings?.api_id) setApiId(data.settings.api_id)
      }
    } catch {}
  }

  useEffect(() => { fetchAccounts(); fetchSettings() }, [])

  // ── Add account ──
  const handleAddAccount = async () => {
    if (!newPhone.trim()) return
    try {
      const form = new FormData()
      form.append('phone', newPhone.trim())
      const res = await fetch(`${API}/api/accounts/add`, { method: 'POST', body: form })
      if (res.ok) {
        setShowModal(false); setNewPhone(''); fetchAccounts()
      } else {
        const err = await res.json(); alert(err.detail || 'Помилка')
      }
    } catch { alert('Бекенд не запущено') }
  }

  // ── Auth flow ──
  const [authError, setAuthError] = useState(null)
  const [authPassword, setAuthPassword] = useState('')

  const handleSendCode = async (phone) => {
    if (!apiConfigured) {
      alert('Спочатку налаштуйте API ID та API Hash (кнопка 🔑 API Settings)')
      return
    }
    setAuthLoading(true)
    setAuthError(null)
    try {
      const form = new FormData()
      form.append('phone', phone)
      const res = await fetch(`${API}/api/accounts/send-code`, { method: 'POST', body: form })
      const data = await res.json()
      if (res.ok) {
        setPhoneHash(data.phone_code_hash)
        if (data.phone) {
          setShowAuthModal(prev => ({ ...prev, phone: data.phone }))
        }
        setAuthStep('code')
      } else {
        setAuthError(data.detail || 'Помилка надсилання коду')
      }
    } catch { setAuthError('Бекенд не відповідає') }
    setAuthLoading(false)
  }

  const handleVerifyCode = async (phone) => {
    setAuthLoading(true)
    setAuthError(null)
    try {
      const form = new FormData()
      form.append('phone', phone)
      form.append('code', authCode)
      form.append('phone_code_hash', phoneHash)
      if (authPassword.trim()) {
        form.append('password', authPassword.trim())
      }
      const res = await fetch(`${API}/api/accounts/verify-code`, { method: 'POST', body: form })
      const data = await res.json()
      if (res.ok) {
        if (data.needs_2fa) {
          setAuthStep('2fa')
          setAuthError(data.message || 'Цей акаунт захищено хмарним паролем (2FA). Введіть його нижче:')
        } else {
          setShowAuthModal(null)
          setAuthStep('phone')
          setAuthCode('')
          setAuthPassword('')
          fetchAccounts()
          alert(`✅ Акаунт ${phone} успішно підключено!`)
        }
      } else {
        setAuthError(data.detail || 'Невірний код')
      }
    } catch { setAuthError('Бекенд не відповідає') }
    setAuthLoading(false)
  }

  // ── API settings ──
  const handleSaveSettings = async () => {
    try {
      const form = new FormData()
      form.append('api_id', apiId)
      form.append('api_hash', apiHash)
      const res = await fetch(`${API}/api/dashboard/settings`, { method: 'POST', body: form })
      if (res.ok) {
        setShowSettingsModal(false); setApiConfigured(true); setApiHash('')
        alert('✅ API ключі збережено!')
      }
    } catch { alert('Бекенд не запущено') }
  }

  // ── Upload .session files ──
  const handleUploadSessions = async (e) => {
    const files = e.target.files
    if (!files.length) return
    const form = new FormData()
    for (const f of files) form.append('files', f)
    try {
      const res = await fetch(`${API}/api/accounts/upload-sessions`, { method: 'POST', body: form })
      if (res.ok) {
        const data = await res.json()
        alert(`✅ Імпортовано ${data.imported} акаунтів`)
        fetchAccounts()
      } else {
        const err = await res.json(); alert(err.detail || 'Помилка')
      }
    } catch { alert('Бекенд не запущено') }
  }

  // ── Delete ──
  const handleDelete = async (id) => {
    if (!confirm('Видалити акаунт?')) return
    try {
      const res = await fetch(`${API}/api/accounts/${id}`, { method: 'DELETE' })
      if (res.ok) fetchAccounts()
      else { const err = await res.json(); alert(err.detail || 'Помилка') }
    } catch { alert('Бекенд не запущено') }
  }

  // ── Check status ──
  const handleCheck = async (acc) => {
    setCheckingId(acc.id)
    try {
      const res = await fetch(`${API}/api/accounts/${acc.id}/check`, { method: 'POST' })
      if (res.ok) fetchAccounts()
    } catch {}
    setCheckingId(null)
  }

  // ── Save proxy ──
  const openProxyModal = (acc) => {
    setProxyForm({
      type: acc.proxy_type || 'socks5',
      host: acc.proxy_host || '',
      port: acc.proxy_port || '',
      username: acc.proxy_username || '',
      password: acc.proxy_password || '',
    })
    setShowProxyModal(acc.id)
  }

  const handleSaveProxy = async () => {
    if (!proxyForm.host || !proxyForm.port) {
      alert('Заповніть хост і порт')
      return
    }
    try {
      const form = new FormData()
      form.append('proxy_type', proxyForm.type)
      form.append('proxy_host', proxyForm.host)
      form.append('proxy_port', proxyForm.port)
      form.append('proxy_username', proxyForm.username)
      form.append('proxy_password', proxyForm.password)
      const res = await fetch(`${API}/api/accounts/${showProxyModal}/proxy`, {
        method: 'PUT', body: form
      })
      if (res.ok) {
        setShowProxyModal(null); fetchAccounts(); alert('✅ Проксі збережено!')
      } else {
        const err = await res.json(); alert(err.detail || 'Помилка')
      }
    } catch { alert('Бекенд не запущено') }
  }

  // ── Join chat ──
  const handleJoinChat = async () => {
    if (!joinLink.trim() || !showJoinModal) return
    setJoinLoading(true)
    setJoinResult(null)
    try {
      const form = new FormData()
      form.append('account_id', showJoinModal.id)
      form.append('chat_link', joinLink.trim())
      const res = await fetch(`${API}/api/accounts/join-chat`, { method: 'POST', body: form })
      const data = await res.json()
      if (res.ok) {
        setJoinResult({ ok: true, msg: `✅ Успішно приєднано до ${joinLink}` })
      } else {
        setJoinResult({ ok: false, msg: data.detail || 'Помилка' })
      }
    } catch { setJoinResult({ ok: false, msg: 'Бекенд не запущено' }) }
    setJoinLoading(false)
  }

  const statusLabel = (s) => ({ active: 'Active', 'spam-block': 'Spam-block', banned: 'Banned', inactive: 'Inactive' }[s] || s)

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Account Manager</h2>
          <p className="subtitle">Управління Telegram-акаунтами</p>
        </div>
        <div className="btn-group">
          <button className="btn btn-secondary btn-sm" onClick={() => setShowSettingsModal(true)}>
            <Key size={14} /> API Settings
          </button>
          <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
            <Upload size={14} /> .session
            <input type="file" multiple accept=".session" style={{ display: 'none' }} onChange={handleUploadSessions} />
          </label>
          <button className="btn btn-primary btn-sm" onClick={() => { setShowModal(true); setNewPhone('') }}>
            <Plus size={14} /> Додати акаунт
          </button>
        </div>
      </div>

      <div className="page-body">
        {!apiConfigured && !loading && (
          <div className="card section" style={{ borderLeft: '3px solid var(--neon-yellow)' }}>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              <strong style={{ color: 'var(--neon-yellow)' }}>⚠️ API не налаштовано:</strong>{' '}
              Для авторизації акаунтів потрібно додати Telegram API ключі.{' '}
              <button style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', textDecoration: 'underline', fontFamily: 'inherit' }} onClick={() => setShowSettingsModal(true)}>
                Налаштувати зараз
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="empty-state"><div className="empty-state-icon">⏳</div><div className="empty-state-text">Завантаження...</div></div>
        ) : accounts.length === 0 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">👤</div>
              <div className="empty-state-text">Немає акаунтів</div>
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '8px' }}>
                Додайте акаунт вручну або завантажте .session файли
              </p>
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th><th>Телефон</th><th>Статус</th><th>Проксі</th>
                    <th>Відправлено</th><th>Інвайтів</th><th>Дії</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map(acc => (
                    <tr key={acc.id}>
                      <td>{acc.id}</td>
                      <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{acc.phone}</td>
                      <td>
                        <span className={`badge ${acc.status}`}>
                          <span className="badge-dot"></span>{statusLabel(acc.status)}
                        </span>
                      </td>
                      <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}>
                        {acc.proxy_host ? `${acc.proxy_type}://${acc.proxy_host}:${acc.proxy_port}` : '—'}
                      </td>
                      <td>{acc.messages_sent_today || 0}/35</td>
                      <td>{acc.invites_sent_today || 0}/15</td>
                      <td>
                        <div className="btn-group">
                          {/* Authorize (inactive accounts) */}
                          {acc.status === 'inactive' && (
                            <button className="btn btn-success btn-sm" title="Авторизувати"
                              onClick={() => { setShowAuthModal(acc); setAuthStep('phone'); setAuthCode('') }}>
                              <LogIn size={13} />
                            </button>
                          )}
                          {/* Check status */}
                          {acc.status !== 'inactive' && (
                            <button className="btn btn-primary btn-sm" title="Перевірити статус"
                              disabled={checkingId === acc.id}
                              onClick={() => handleCheck(acc)}>
                              <RefreshCw size={13} className={checkingId === acc.id ? 'spin' : ''} />
                            </button>
                          )}
                          {/* Join chat */}
                          {acc.status === 'active' && (
                            <button className="btn btn-secondary btn-sm" title="Вступити в чат/канал"
                              onClick={() => { setShowJoinModal(acc); setJoinLink(''); setJoinResult(null) }}>
                              🔗
                            </button>
                          )}
                          {/* Proxy */}
                          <button className="btn btn-secondary btn-sm" title="Проксі" onClick={() => openProxyModal(acc)}>
                            <Shield size={13} />
                          </button>
                          {/* Delete */}
                          <button className="btn btn-danger btn-sm" title="Видалити" onClick={() => handleDelete(acc.id)}>
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ── Add Account Modal ── */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal fade-in" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">Додати акаунт</h3>
            <div className="input-group">
              <label className="input-label">Номер телефону</label>
              <input className="input" placeholder="+380XXXXXXXXX" value={newPhone}
                onChange={e => setNewPhone(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddAccount()} />
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowModal(false)}>Скасувати</button>
              <button className="btn btn-primary" onClick={handleAddAccount} disabled={!newPhone.trim()}>Додати</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Auth Modal ── */}
      {showAuthModal && (
        <div className="modal-overlay" onClick={() => { setShowAuthModal(null); setAuthError(null) }}>
          <div className="modal fade-in" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">Авторизація: {showAuthModal.phone}</h3>
            
            {authError && (
              <div style={{
                background: 'rgba(255,71,87,0.12)', border: '1px solid rgba(255,71,87,0.3)',
                borderRadius: '8px', padding: '10px 14px', marginBottom: '14px',
                color: '#ff6b7a', fontSize: '13px', lineHeight: '1.4'
              }}>
                {authError}
              </div>
            )}

            {authStep === 'phone' && (
              <>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                  Telegram надішле код підтвердження на <strong style={{ color: 'var(--text-primary)' }}>{showAuthModal.phone}</strong> (у додаток Telegram або SMS).
                </p>
                <div className="modal-actions">
                  <button className="btn btn-secondary" onClick={() => setShowAuthModal(null)}>Скасувати</button>
                  <button className="btn btn-primary" disabled={authLoading}
                    onClick={() => handleSendCode(showAuthModal.phone)}>
                    {authLoading ? '⏳ Відправляємо...' : '📩 Надіслати код'}
                  </button>
                </div>
              </>
            )}

            {authStep === 'code' && (
              <>
                <div className="input-group">
                  <label className="input-label">Код з додатку Telegram або SMS</label>
                  <input className="input" placeholder="12345" value={authCode}
                    onChange={e => setAuthCode(e.target.value)}
                    autoFocus
                    onKeyDown={e => e.key === 'Enter' && handleVerifyCode(showAuthModal.phone)} />
                </div>
                <div className="modal-actions">
                  <button className="btn btn-secondary" onClick={() => { setAuthStep('phone'); setAuthError(null) }}>Назад</button>
                  <button className="btn btn-primary" disabled={!authCode.trim() || authLoading}
                    onClick={() => handleVerifyCode(showAuthModal.phone)}>
                    {authLoading ? '⏳ Перевірка...' : '✓ Підтвердити'}
                  </button>
                </div>
              </>
            )}

            {authStep === '2fa' && (
              <>
                <div className="input-group">
                  <label className="input-label">Хмарний пароль (2FA Password)</label>
                  <input className="input" type="password" placeholder="Ваш пароль 2FA..." value={authPassword}
                    onChange={e => setAuthPassword(e.target.value)}
                    autoFocus
                    onKeyDown={e => e.key === 'Enter' && handleVerifyCode(showAuthModal.phone)} />
                </div>
                <div className="modal-actions">
                  <button className="btn btn-secondary" onClick={() => { setAuthStep('code'); setAuthError(null) }}>Назад</button>
                  <button className="btn btn-primary" disabled={!authPassword.trim() || authLoading}
                    onClick={() => handleVerifyCode(showAuthModal.phone)}>
                    {authLoading ? '⏳ Вхід...' : 'Увійти з паролем'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── API Settings Modal ── */}
      {showSettingsModal && (
        <div className="modal-overlay" onClick={() => setShowSettingsModal(false)}>
          <div className="modal fade-in" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">🔑 Telegram API Settings</h3>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Отримайте ключі на{' '}
              <a href="https://my.telegram.org" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
                my.telegram.org
              </a>{' '}→ API development tools
            </p>
            <div className="input-group">
              <label className="input-label">API ID</label>
              <input className="input" placeholder="12345678" value={apiId} onChange={e => setApiId(e.target.value)} />
            </div>
            <div className="input-group">
              <label className="input-label">API Hash</label>
              <input className="input" placeholder="abc123def456..." value={apiHash} onChange={e => setApiHash(e.target.value)} />
            </div>
            {apiConfigured && (
              <div style={{ fontSize: '12px', color: 'var(--neon-green)', marginBottom: '8px' }}>✅ API ключі вже збережені</div>
            )}
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowSettingsModal(false)}>Скасувати</button>
              <button className="btn btn-primary" onClick={handleSaveSettings} disabled={!apiId.trim() || !apiHash.trim()}>Зберегти</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Proxy Modal ── */}
      {showProxyModal && (
        <div className="modal-overlay" onClick={() => setShowProxyModal(null)}>
          <div className="modal fade-in" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">🛡️ Налаштування проксі</h3>
            <div className="form-grid">
              <div className="input-group">
                <label className="input-label">Тип</label>
                <select className="select" value={proxyForm.type} onChange={e => setProxyForm(p => ({ ...p, type: e.target.value }))}>
                  <option value="socks5">SOCKS5</option>
                  <option value="socks4">SOCKS4</option>
                  <option value="http">HTTP</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">Хост</label>
                <input className="input" placeholder="192.168.1.1" value={proxyForm.host}
                  onChange={e => setProxyForm(p => ({ ...p, host: e.target.value }))} />
              </div>
              <div className="input-group">
                <label className="input-label">Порт</label>
                <input className="input" placeholder="1080" type="number" value={proxyForm.port}
                  onChange={e => setProxyForm(p => ({ ...p, port: e.target.value }))} />
              </div>
              <div className="input-group">
                <label className="input-label">Логін (опційно)</label>
                <input className="input" placeholder="username" value={proxyForm.username}
                  onChange={e => setProxyForm(p => ({ ...p, username: e.target.value }))} />
              </div>
              <div className="input-group">
                <label className="input-label">Пароль (опційно)</label>
                <input className="input" type="password" placeholder="password" value={proxyForm.password}
                  onChange={e => setProxyForm(p => ({ ...p, password: e.target.value }))} />
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowProxyModal(null)}>Скасувати</button>
              <button className="btn btn-primary" onClick={handleSaveProxy}>💾 Зберегти</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Join Chat Modal ── */}
      {showJoinModal && (
        <div className="modal-overlay" onClick={() => { setShowJoinModal(null); setJoinResult(null) }}>
          <div className="modal fade-in" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">🔗 Вступити в чат / канал</h3>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              Акаунт: <strong>{showJoinModal.phone}</strong>
            </p>
            <div className="input-group">
              <label className="input-label">Посилання або @username</label>
              <input className="input" placeholder="https://t.me/channel або @username"
                value={joinLink} onChange={e => setJoinLink(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleJoinChat()} />
            </div>
            {joinResult && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 14px', borderRadius: 8, marginTop: 8,
                background: joinResult.ok ? 'rgba(46,213,115,0.1)' : 'rgba(255,71,87,0.1)',
                color: joinResult.ok ? '#2ed573' : '#ff4757',
                border: `1px solid ${joinResult.ok ? 'rgba(46,213,115,0.3)' : 'rgba(255,71,87,0.3)'}`,
                fontSize: 13,
              }}>
                {joinResult.ok ? <CheckCircle size={16} /> : <XCircle size={16} />}
                {joinResult.msg}
              </div>
            )}
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowJoinModal(null)}>Закрити</button>
              <button className="btn btn-primary" disabled={!joinLink.trim() || joinLoading}
                onClick={handleJoinChat}>
                {joinLoading ? 'Підключення...' : '🔗 Вступити'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
