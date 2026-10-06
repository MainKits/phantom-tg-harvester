import { useState, useEffect } from 'react'
import { Key, Plus, X, Copy, CheckCircle2, Shield, RefreshCw, Trash2, Search } from 'lucide-react'
import { API } from '../apiConfig'

const MASTER = 'phantom_master_2025' // must match backend

export default function AdminLicense() {
  const [keys, setKeys] = useState([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [note, setNote] = useState('')
  const [search, setSearch] = useState('')
  const [generating, setGenerating] = useState(false)
  const [newKey, setNewKey] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    fetchKeys()
  }, [])

  const fetchKeys = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/license/all?master_token=${MASTER}`)
      const data = await res.json()
      if (Array.isArray(data)) {
        setKeys(data)
      } else {
        console.error('License fetch response:', data)
      }
    } catch (err) {
      console.error('Failed to fetch keys:', err)
    } finally {
      setLoading(false)
    }
  }

  const generateKey = async () => {
    setGenerating(true)
    setNewKey(null)
    try {
      const fd = new FormData()
      fd.append('days', days)
      fd.append('note', note)
      fd.append('master_token', MASTER)
      const res = await fetch(`${API}/api/license/generate`, { method: 'POST', body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Помилка створення ключа')
      setNewKey(data.key)
      setNote('')
      // Immediately refresh the keys list
      await fetchKeys()
    } catch (err) {
      alert(err.message)
    } finally {
      setGenerating(false)
    }
  }

  const revokeKey = async (key) => {
    if (!confirm(`Заблокувати ключ ${key}?`)) return
    try {
      const fd = new FormData()
      fd.append('key', key)
      fd.append('master_token', MASTER)
      await fetch(`${API}/api/license/revoke`, { method: 'POST', body: fd })
      await fetchKeys()
    } catch (err) {
      alert('Помилка блокування')
    }
  }

  const deleteKey = async (key) => {
    if (!confirm(`Назавжди видалити ключ ${key}? Цю дію неможливо скасувати.`)) return
    try {
      const fd = new FormData()
      fd.append('key', key)
      fd.append('master_token', MASTER)
      await fetch(`${API}/api/license/delete`, { method: 'POST', body: fd })
      await fetchKeys()
    } catch (err) {
      alert('Помилка видалення ключа')
    }
  }

  const copyKey = (k) => {
    navigator.clipboard.writeText(k)
    setCopied(k)
    setTimeout(() => setCopied(null), 2000)
  }

  const statusColor = (s) => ({ active: '#2ed573', used: '#ffa502', revoked: '#ff4757' }[s] || '#888')

  const filteredKeys = keys.filter(k => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return (
      (k.key && k.key.toLowerCase().includes(q)) ||
      (k.note && k.note.toLowerCase().includes(q)) ||
      (k.status && k.status.toLowerCase().includes(q))
    )
  })

  return (
    <div className="page-container fade-in">
      <header className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>⚙️ License Admin Panel</h1>
          <p>Генеруйте та керуйте ліцензійними ключами (синхронізація з Supabase Cloud)</p>
        </div>
        <button
          className="btn btn-secondary"
          onClick={fetchKeys}
          disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
          {loading ? 'Оновлення...' : 'Оновити список'}
        </button>
      </header>

      <div className="grid-2">
        {/* Generate section */}
        <div className="card">
          <h2><Key size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />Генерувати новий ключ</h2>

          <div className="form-group" style={{ marginTop: 20 }}>
            <label>Термін дії (днів)</label>
            <select className="input" value={days} onChange={e => setDays(+e.target.value)}>
              <option value={7}>7 днів</option>
              <option value={14}>14 днів</option>
              <option value={30}>30 днів (1 місяць)</option>
              <option value={90}>90 днів (3 місяці)</option>
              <option value={180}>180 днів (6 місяців)</option>
              <option value={365}>365 днів (1 рік)</option>
              <option value={3650}>10 років (Безлімітно)</option>
            </select>
          </div>

          <div className="form-group">
            <label>Нотатка (покупець, контакти, ціна…)</label>
            <input
              type="text"
              className="input"
              placeholder="Наприклад: @client_username / $50"
              value={note}
              onChange={e => setNote(e.target.value)}
            />
          </div>

          <button className="btn btn-primary" style={{ width: '100%', padding: 14 }} onClick={generateKey} disabled={generating}>
            <Plus size={18} /> {generating ? 'Генерація та збереження в хмару...' : 'Згенерувати ключ'}
          </button>

          {newKey && (
            <div style={{ marginTop: 20, padding: '16px 20px', background: 'rgba(46,213,115,0.1)', border: '1px solid rgba(46,213,115,0.3)', borderRadius: 12 }}>
              <p style={{ margin: '0 0 8px', color: '#2ed573', fontWeight: 700 }}>✅ Ключ створено і збережено у базі даних!</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <code style={{ flex: 1, fontSize: 18, letterSpacing: 2, color: '#fff', fontWeight: 800 }}>{newKey}</code>
                <button className="btn btn-secondary" style={{ padding: '8px 12px' }} onClick={() => copyKey(newKey)}>
                  {copied === newKey ? <CheckCircle2 size={16} color="#2ed573" /> : <Copy size={16} />}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="card">
          <h2><Shield size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />Статистика ліцензій</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 20 }}>
            {[
              { label: 'Всього ключів', value: keys.length, color: '#8400ff' },
              { label: 'Активних', value: keys.filter(k => k.status === 'active').length, color: '#2ed573' },
              { label: 'Використаних', value: keys.filter(k => k.status === 'used').length, color: '#ffa502' },
              { label: 'Заблокованих', value: keys.filter(k => k.status === 'revoked').length, color: '#ff4757' },
            ].map(s => (
              <div key={s.label} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 12, padding: '16px 20px', border: `1px solid ${s.color}33` }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 13, color: '#888', marginTop: 4 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Keys table */}
      <div className="card" style={{ marginTop: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <h2>Всі ліцензійні ключі ({filteredKeys.length} з {keys.length})</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 260 }}>
            <div style={{ position: 'relative', width: '100%' }}>
              <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#666' }} />
              <input
                type="text"
                className="input"
                placeholder="Пошук за ключем чи нотаткою..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ paddingLeft: 36, margin: 0 }}
              />
            </div>
          </div>
        </div>

        <div style={{ overflowX: 'auto', marginTop: 16 }}>
          {loading && keys.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#888' }}>
              <RefreshCw size={24} className="spin" style={{ marginBottom: 12 }} />
              <p>Завантаження ключів з бази даних...</p>
            </div>
          ) : filteredKeys.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#888' }}>
              <p>Ключів не знайдено</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #333' }}>
                  {['Ключ', 'Статус', 'Активовано', 'Діє до', 'Нотатка', 'Дії'].map(h => (
                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', color: '#888', fontSize: 13, fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredKeys.map(k => (
                  <tr key={k.key} style={{ borderBottom: '1px solid #1e1e1e' }}>
                    <td style={{ padding: '12px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <code style={{ fontSize: 13, letterSpacing: 1.5, color: '#fff', fontWeight: 600 }}>{k.key}</code>
                        <button
                          onClick={() => copyKey(k.key)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#888', padding: 2 }}
                          title="Скопіювати ключ"
                        >
                          {copied === k.key ? <CheckCircle2 size={15} color="#2ed573" /> : <Copy size={15} />}
                        </button>
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <span style={{ padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 700, color: statusColor(k.status), background: statusColor(k.status) + '22' }}>
                        {k.status}
                      </span>
                    </td>
                    <td style={{ padding: '12px 14px', color: '#888', fontSize: 13 }}>
                      {k.activated_at ? new Date(k.activated_at).toLocaleDateString('uk-UA') : '—'}
                    </td>
                    <td style={{ padding: '12px 14px', color: '#888', fontSize: 13 }}>
                      {k.expires_at ? new Date(k.expires_at).toLocaleDateString('uk-UA') : '—'}
                    </td>
                    <td style={{ padding: '12px 14px', color: '#aaa', fontSize: 13 }}>
                      {k.note || '—'}
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {k.status !== 'revoked' && (
                          <button
                            onClick={() => revokeKey(k.key)}
                            style={{
                              background: 'rgba(255,165,2,0.1)',
                              border: '1px solid rgba(255,165,2,0.3)',
                              borderRadius: 8,
                              color: '#ffa502',
                              cursor: 'pointer',
                              padding: '5px 10px',
                              fontSize: 12,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4
                            }}
                            title="Заблокувати цей ключ"
                          >
                            <X size={13} /> Блок
                          </button>
                        )}
                        <button
                          onClick={() => deleteKey(k.key)}
                          style={{
                            background: 'rgba(255,71,87,0.1)',
                            border: '1px solid rgba(255,71,87,0.3)',
                            borderRadius: 8,
                            color: '#ff4757',
                            cursor: 'pointer',
                            padding: '5px 8px',
                            fontSize: 12,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4
                          }}
                          title="Видалити ключ назавжди"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
